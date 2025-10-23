"""
Command Validator - A fluent API for validating and parsing commands

This module provides a flexible command validation system with a fluent interface.
Example usage:
    validator = CommandValidator()
    validator.add_command("protocol") \
        .integer("protocol_number", minimum=0, maximum=11, description="protocol number") \
        .integer("payload_length", required=lambda f: f.protocol_number >= 9, 
                 minimum=4, maximum=64, description="payload length")
"""


class ValidationError(Exception):
    """Raised when command validation fails"""
    pass


class CommandField:
    """Represents a single field in a command"""
    
    def __init__(self, name, field_type, minimum=None, maximum=None, 
                 required=None, description=None, default=None):
        self.name = name
        self.field_type = field_type
        self.minimum = minimum
        self.maximum = maximum
        self.required = required  # Can be bool or callable
        self.description = description
        self.default = default
    
    def validate(self, value, parsed_values):
        """Validate a field value"""
        # Check if field is required
        is_required = self.required
        if callable(is_required):
            is_required = is_required(parsed_values)
        
        if value is None:
            if is_required:
                raise ValidationError(f"Field '{self.name}' is required")
            return self.default
        
        # Type validation and conversion
        if self.field_type == "integer":
            try:
                value = int(value)
            except (ValueError, TypeError):
                raise ValidationError(f"Field '{self.name}' must be an integer")
            
            if self.minimum is not None and value < self.minimum:
                raise ValidationError(
                    f"Field '{self.name}' must be at least {self.minimum}"
                )
            if self.maximum is not None and value > self.maximum:
                raise ValidationError(
                    f"Field '{self.name}' must be at most {self.maximum}"
                )
        
        elif self.field_type == "string":
            value = str(value)
        
        return value


class ParsedValues:
    """Container for parsed command values with attribute access"""
    
    def __init__(self, values_dict):
        self._values = values_dict
    
    def __getattr__(self, name):
        if name.startswith('_'):
            return object.__getattribute__(self, name)
        return self._values.get(name)
    
    def __getitem__(self, key):
        return self._values[key]
    
    def get(self, key, default=None):
        return self._values.get(key, default)
    
    def __contains__(self, key):
        return key in self._values
    
    def __repr__(self):
        return f"ParsedValues({self._values})"


class Command:
    """Represents a command with its fields"""
    
    def __init__(self, name, validator):
        self.name = name
        self.fields = []
        self.validator = validator
        self.handler = None
    
    def integer(self, name, minimum=None, maximum=None, required=True, 
                description=None, default=None):
        """Add an integer field to the command"""
        field = CommandField(
            name=name,
            field_type="integer",
            minimum=minimum,
            maximum=maximum,
            required=required,
            description=description,
            default=default
        )
        self.fields.append(field)
        return self
    
    def string(self, name, required=True, description=None, default=None):
        """Add a string field to the command"""
        field = CommandField(
            name=name,
            field_type="string",
            required=required,
            description=description,
            default=default
        )
        self.fields.append(field)
        return self
    
    def set_handler(self, handler):
        """Set the handler function for this command"""
        self.handler = handler
        return self
    
    def parse(self, args):
        """Parse command arguments according to field definitions"""
        parsed = {}
        parsed_values = ParsedValues(parsed)
        
        for i, field in enumerate(self.fields):
            value = None
            if i < len(args):
                value = args[i]
                # Handle special default marker
                if value == "-":
                    value = None
            
            try:
                parsed[field.name] = field.validate(value, parsed_values)
            except ValidationError as e:
                raise ValidationError(f"Command '{self.name}': {str(e)}")
        
        return ParsedValues(parsed)
    
    def execute(self, args):
        """Parse arguments and execute the handler"""
        parsed = self.parse(args)
        if self.handler:
            return self.handler(parsed)
        return None


class CommandValidator:
    """Main command validator class with fluent API"""
    
    def __init__(self):
        self.commands = {}
    
    def add_command(self, name):
        """Add a new command and return it for chaining"""
        command = Command(name, self)
        self.commands[name] = command
        return command
    
    def get_command(self, name):
        """Get a command by name"""
        return self.commands.get(name)
    
    def has_command(self, name):
        """Check if a command exists"""
        return name in self.commands
    
    def parse(self, command_string):
        """Parse a command string and return the command name and parsed values"""
        parts = command_string.strip().split()
        if not parts:
            raise ValidationError("Empty command")
        
        cmd_name = parts[0]
        if not cmd_name.startswith("/"):
            raise ValidationError(f"Command must start with /")
        
        cmd_name = cmd_name[1:]  # Remove the leading /
        
        if cmd_name not in self.commands:
            raise ValidationError(f"Unknown command: /{cmd_name}")
        
        command = self.commands[cmd_name]
        args = parts[1:]
        
        return cmd_name, command.parse(args)
    
    def execute(self, command_string):
        """Parse and execute a command"""
        cmd_name, parsed = self.parse(command_string)
        command = self.commands[cmd_name]
        if command.handler:
            return command.handler(parsed)
        return None
    
    def validate_command(self, command_string):
        """Validate a command string without executing it"""
        try:
            self.parse(command_string)
            return True
        except ValidationError:
            return False
