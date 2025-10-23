"""
Main application entry point for data_over_sound.

This module provides an interactive command-line interface for transmitting
and receiving data over sound waves.
"""

import gw
import parse
from webbrowser import open as wopen
import os
from sys import exit
from command_validator import CommandValidator, ValidationError


class Output:
    """
    Handler for received data output.
    
    Stores received data and provides parsing capabilities.
    """
    
    def __init__(self):
        self.data = ""

    def data_callback(self, data):
        """
        Callback function for received data.
        
        Args:
            data: Received data string
        """
        self.data = data
        print(data)

    def parse(self):
        """
        Parse stored data for URLs, emails, and phone numbers.
        
        Returns:
            dict: Dictionary with 'urls', 'emails', and 'phones' keys
        """
        return parse.extract_info(self.data)

output = Output()
g=gw.GW(output.data_callback)
g.start()

# Initialize command validator
validator = CommandValidator()


# Define commands using decorators
@validator.command("p")
@validator.integer("protocol_number", minimum=0, maximum=11)
@validator.integer("payload_length", 
                   required=lambda f: f.protocol_number >= 9,
                   minimum=4, maximum=64,
                   default=None)
def handle_protocol_command(parsed):
    """Set protocol and payload length. Payload length is optional and must be between 4 and 64. It is only required for protocols 9 to 11 but can be set for all protocols"""
    g.protocol = parsed.protocol_number
    toreturn = f"protocol set to {g.protocol}. "
    
    if parsed.payload_length is not None:
        g.switchinstance(parsed.payload_length)
        return toreturn + f"payload length {parsed.payload_length}"
    else:
        g.switchinstance(-1)
        return toreturn


@validator.command("reset")
def handle_reset_command(parsed):
    """Reset the instance. If data starts to get corrupted, this command can be used to reset the instance"""
    g.switchinstance(-1)
    return "instance reset"


@validator.command("open")
def handle_open_command(parsed):
    """Open URLs, emails, and phone numbers in the default web browser, email client, and phone dialer respectively. Use this command if a url, email, or phone number is received. Use it on your own risk, as it may open malicious websites"""
    result = output.parse()
    
    # Show what will be opened and ask for confirmation
    items_to_open = []
    if result["urls"]:
        items_to_open.extend([f"URL: {url}" for url in result["urls"]])
    if result["emails"]:
        items_to_open.extend([f"Email: {email}" for email in result["emails"]])
    if result["phones"]:
        items_to_open.extend([f"Phone: {phone}" for phone in result["phones"]])
    
    if not items_to_open:
        return "No URLs, emails, or phone numbers found to open"
    
    print("\nThe following items will be opened:")
    for item in items_to_open:
        print(f"  - {item}")
    
    confirmation = input("Are you sure you want to open these? (y/N): ")
    if confirmation.lower() != 'y':
        return "Cancelled"
    
    # Open items after confirmation
    for url in result["urls"]:
        try:
            wopen(url)
        except Exception as e:
            print(f"Error opening URL {url}: {e}")
    
    for email in result["emails"]:
        try:
            wopen(f"mailto:{email}")
        except Exception as e:
            print(f"Error opening email {email}: {e}")
    
    for phone in result["phones"]:
        try:
            wopen(f"tel:{phone}")
        except Exception as e:
            print(f"Error opening phone {phone}: {e}")
    
    return "Opened"


@validator.command("exit")
def handle_exit_command(parsed):
    """Exit the program"""
    g.stop()
    exit()


@validator.command("device")
def handle_device_command(parsed):
    """Test sound devices"""
    try:
        os.remove("devices.json")
    except FileNotFoundError:
        pass  # File already deleted, no problem
    except OSError as e:
        return f"Error removing devices.json: {e}"
    input("!Press enter and restart the program. It will start with the device test prompt.")
    g.stop()
    exit()


@validator.command("help")
def handle_help_command(parsed):
    """Display this message"""
    return validator.generate_help()


@validator.command("sendhelp")
def handle_sendhelp_command(parsed):
    """Sends each line of this message as a separate message via sound"""
    help_text = validator.generate_help()
    for i in help_text.split("\n"):
        g.send(i)
    return "sending"


def command(cmd):
    """Process a command or message"""
    if not cmd.startswith("/"):
        g.send(cmd)
        return "sending"
    
    try:
        return validator.execute(cmd)
    except ValidationError as e:
        return str(e)
    except Exception as e:
        return str(e)

def main():
    """Main application loop."""
    print("Welcome to data_over_sound")
    print("Type /help for help")
    print("Enter your message or command:")
    
    try:
        while True:
            try:
                cmd = input()
                result = command(cmd)
                if result:
                    print(result)
            except EOFError:
                # End of input stream
                break
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Graceful cleanup
        try:
            g.stop()
        except Exception as e:
            print(f"Error during cleanup: {e}")


if __name__ == "__main__":
    main()