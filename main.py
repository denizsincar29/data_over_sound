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

help = """
/p [protocol number] [payload length] - set protocol and payload length. payload length is optional and must be between 4 and 64. It is only required for protocols 9 to 11 but can be set for all protocols
/reset - reset the instance. If data starts to get corrupted, this command can be used to reset the instance
/open - open URLs, emails, and phone numbers in the default web browser, email client, and phone dialer respectively. Use this command if a url, email, or phone number is received. Use it on your own risk, as it may open malicious websites
/exit - exit the program
/device - test sound devices
/help - display this message
/sendhelp - sends each line of this message as a separate message via sound
"""

# Initialize command validator
validator = CommandValidator()

# Define /p command (protocol)
validator.add_command("p") \
    .integer("protocol_number", minimum=0, maximum=11, description="protocol number") \
    .integer("payload_length", 
             required=lambda f: f.protocol_number >= 9,
             minimum=4, maximum=64, 
             description="payload length",
             default=None)

# Define /reset command
validator.add_command("reset")

# Define /open command
validator.add_command("open")

# Define /exit command
validator.add_command("exit")

# Define /device command
validator.add_command("device")

# Define /help command
validator.add_command("help")

# Define /sendhelp command
validator.add_command("sendhelp")


def handle_protocol_command(parsed):
    """Handler for /p command"""
    g.protocol = parsed.protocol_number
    toreturn = f"protocol set to {g.protocol}. "
    
    if parsed.payload_length is not None:
        g.switchinstance(parsed.payload_length)
        return toreturn + f"payload length {parsed.payload_length}"
    else:
        g.switchinstance(-1)
        return toreturn


def handle_reset_command(parsed):
    """Handler for /reset command"""
    g.switchinstance(-1)
    return "instance reset"


def handle_open_command(parsed):
    """Handler for /open command"""
    result = output.parse()
    for url in result["urls"]:
        wopen(url)
    for email in result["emails"]:
        wopen("mailto:"+email)
    for phone in result["phones"]:
        wopen("tel:"+phone)
    return "opening"


def handle_exit_command(parsed):
    """Handler for /exit command"""
    g.stop()
    exit()


def handle_device_command(parsed):
    """Handler for /device command"""
    os.remove("devices.json")
    input("!Press enter and restart the program. It will start with the device test prompt.")
    g.stop()
    exit()


def handle_help_command(parsed):
    """Handler for /help command"""
    return help


def handle_sendhelp_command(parsed):
    """Handler for /sendhelp command"""
    for i in help.split("\n"):
        g.send(i)
    return "sending"


# Register handlers
validator.get_command("p").set_handler(handle_protocol_command)
validator.get_command("reset").set_handler(handle_reset_command)
validator.get_command("open").set_handler(handle_open_command)
validator.get_command("exit").set_handler(handle_exit_command)
validator.get_command("device").set_handler(handle_device_command)
validator.get_command("help").set_handler(handle_help_command)
validator.get_command("sendhelp").set_handler(handle_sendhelp_command)


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