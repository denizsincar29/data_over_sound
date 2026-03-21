"""
Main application entry point for data_over_sound.

This module provides an interactive command-line interface for transmitting
and receiving data over sound waves.
"""

import gw
import parse
from webbrowser import open as wopen
import os
import time
from sys import exit
from command_validator import CommandValidator, ValidationError
from file_sharing import FileSender, FileReceiver, FileSharingProtocol, try_to_utf8


class Output:
    """
    Handler for received data output.

    Stores received data and provides parsing capabilities.
    """

    def __init__(self):
        self.data = ""
        self.receiver = None
        self.sender = None

    def data_callback(self, data):
        """
        Callback function for received data.

        Args:
            data: Received data string
        """
        if self.sender and self.sender.state != "DONE":
            if self.sender.handle_response(data):
                return

        if self.receiver:
            res = self.receiver.handle_data(data)
            if res:
                if res == "HANDSHAKE_RECEIVED":
                    print(f"Receiving file: {self.receiver.filename} ({self.receiver.num_chunks} chunks)")
                elif res == "SUCCESS":
                    print(f"File received successfully: {self.receiver.filename}")
                    self.receiver.reset()
                return

        self.data = try_to_utf8(data)
        print(self.data)

    def parse(self):
        """
        Parse stored data for URLs, emails, and phone numbers.

        Returns:
            dict: Dictionary with 'urls', 'emails', and 'phones' keys
        """
        return parse.extract_info(self.data)

output = Output()
g=gw.GW(output.data_callback)
output.receiver = FileReceiver(g)
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


@validator.command("sendfile")
@validator.string("filepath")
def handle_sendfile_command(parsed):
    """Send a file over sound. Usage: /sendfile <filepath>"""
    if not os.path.exists(parsed.filepath):
        return f"File not found: {parsed.filepath}"

    sender = FileSender(g, parsed.filepath)
    output.sender = sender
    print(f"Starting handshake for {sender.filename}...")
    sender.send_handshake()

    # Wait for ready signal
    start_time = time.time()
    while sender.state == "WAITING_FOR_READY" and time.time() - start_time < 30:
        time.sleep(0.1)

    if sender.state == "WAITING_FOR_READY":
        output.sender = None
        return "Handshake timeout (30s). Make sure the receiver is listening."

    print("Handshake successful, sending chunks...")
    # send_all_chunks was called in handle_response when READY was received

    # Wait for completion or retransmission requests
    start_time = time.time()
    while sender.state == "WAITING_FOR_ACK" and time.time() - start_time < 60: # 60s for file transfer
        time.sleep(0.1)
        # reset timer if we are still active? No, let's keep it simple for now.

    if sender.state == "DONE":
        output.sender = None
        return f"File {sender.filename} sent successfully."
    else:
        output.sender = None
        return f"File transfer timed out or failed. State: {sender.state}"


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
                # Use small timeout for input to check for receiver timeouts
                # select.select on sys.stdin works on Unix but not on Windows.
                # To be portable, we use a more cross-platform approach if possible,
                # but since we're in a single-threaded loop, we'll try/except for now.
                import select
                import sys

                readable = []
                try:
                    readable, _, _ = select.select([sys.stdin], [], [], 0.1)
                except (ValueError, select.error):
                    # On Windows select on stdin might fail.
                    # Fallback to a blocking input if we have to,
                    # or handle it differently if it's a known non-unix environment.
                    cmd = input()
                    result = command(cmd)
                    if result:
                        print(result)
                    readable = [] # Already handled

                if readable:
                    cmd = sys.stdin.readline().strip()
                    if cmd:
                        result = command(cmd)
                        if result:
                            print(result)

                # Check for receiver timeouts
                res = output.receiver.check_timeout()
                if res == "SENT_NACK":
                    print(f"Still waiting for chunks of {output.receiver.filename}. Sent NACK.")

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