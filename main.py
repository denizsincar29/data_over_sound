import gw
import parse
from webbrowser import open as wopen
import os
from sys import exit  # stupid pyinstaller bug, it doesn't work without this line
from command_validator import CommandValidator, ValidationError

class Output:
    def __init__(self):
        self.data = ""

    def data_callback(self, data):
        self.data = data
        print(data)

    def parse(self):
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
    for url in result["urls"]:
        wopen(url)
    for email in result["emails"]:
        wopen("mailto:"+email)
    for phone in result["phones"]:
        wopen("tel:"+phone)
    return "opening"


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

try:
    print("Welcome to data_over_sound")
    print("Type /help for help")
    print("enter your message or command:")
    while True:
        cmd=input()  # don't show > prompt because it prints something else in another thread
        print(command(cmd))
except (KeyboardInterrupt, EOFError):
    g.stop()
    exit()