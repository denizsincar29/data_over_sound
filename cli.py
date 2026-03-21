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
import threading
from sys import exit
from command_validator import CommandValidator, ValidationError
from file_sharing import FileSender, FileReceiver, FileSharingProtocol, try_to_utf8
from settings_manager import settings
from screen_reader_manager import screen_reader
from command_manager import command_manager, AppAPI


def delayed_send(gw_instance, data, protocol=None, delay=0.5):
    """Sends data after a delay in a separate thread to avoid blocking."""
    def _send():
        time.sleep(delay)
        gw_instance.send(data, protocol=protocol)
    threading.Thread(target=_send, daemon=True).start()


class Output:
    """
    Handler for received data output.

    Stores received data and provides parsing capabilities.
    """

    def __init__(self, gw_instance=None):
        self.data = ""
        self.receiver = None
        self.sender = None
        self.gw = gw_instance
        self.query_active = False
        self.query_functions = []
        self.query_last_received = 0

    def data_callback(self, data):
        """
        Callback function for received data.

        Args:
            data: Received data string
        """
        text = try_to_utf8(data)

        # Handle remote query
        if text == "__QUERY_REMOTE__":
            if not settings.get("enable_remote_commands", False):
                return
            def respond():
                time.sleep(0.5) # SAR delay
                funcs = command_manager.get_remote_functions()
                for f in funcs:
                    self.gw.send(f)
                    time.sleep(1)
                self.gw.send("$EOF")
            threading.Thread(target=respond, daemon=True).start()
            return

        if self.query_active:
            if text == "$EOF":
                self.query_active = False
                msg = f"Remote functions received: {', '.join(self.query_functions)}"
                print(msg)
                screen_reader.speak(msg)
            else:
                self.query_functions.append(text)
                self.query_last_received = time.time()
                print(f"Remote function: {text}")
                screen_reader.speak(f"Remote function: {text}")
            return

        if text.startswith("__REMOTE__:"):
            if not settings.get("enable_remote_commands", False):
                print("Received remote command, but feature is disabled in settings.")
                return
            try:
                parts = text.split(":")
                cmd_name = parts[1]
                args = parts[2] if len(parts) > 2 else ""
                print(f"Executing Remote Command: {cmd_name} {args}")
                result = command_manager.execute(cmd_name, *([args] if args else []))
                print(f"Command Result: {result}")
                return
            except (ValueError, IndexError) as e:
                print(f"Error parsing remote command: {e}")
                return

        if text.startswith("__RPC__:"):
            try:
                parts = text.split(":")
                protocol = int(parts[1])
                payload = int(parts[2])
                print(f"Received Remote Protocol Change: Protocol {protocol}, Payload {payload}")
                self.gw.protocol = protocol
                settings.set("protocol", protocol)
                settings.set("payload_length", payload)
                self.gw.switchinstance(payload)
                return
            except (ValueError, IndexError):
                pass

        if self.sender and self.sender.state != "DONE":
            action, details = self.sender.handle_response(data)
            if action == "START_SENDING":
                def send_all():
                    time.sleep(0.5) # SAR delay
                    for i in range(self.sender.num_chunks):
                        self.gw.send(self.sender.get_chunk_data(i), protocol=FileSharingProtocol.FILE_PROTOCOL)
                    self.gw.send(self.sender.get_eof_data(), protocol=FileSharingProtocol.FILE_PROTOCOL)
                threading.Thread(target=send_all, daemon=True).start()
                return
            elif action == "RESEND_CHUNKS":
                def resend():
                    time.sleep(0.5) # SAR delay
                    for i in details:
                        self.gw.send(self.sender.get_chunk_data(i), protocol=FileSharingProtocol.FILE_PROTOCOL)
                    self.gw.send(self.sender.get_eof_data(), protocol=FileSharingProtocol.FILE_PROTOCOL)
                threading.Thread(target=resend, daemon=True).start()
                return
            elif action == "COMPLETED":
                return

        if self.receiver:
            status, details = self.receiver.handle_data(data)
            if status:
                if status == "SEND_READY":
                    msg = f"Receiving file: {self.receiver.filename} ({self.receiver.num_chunks} chunks)"
                    print(msg)
                    screen_reader.speak(msg)
                    delayed_send(self.gw, FileSharingProtocol.CONTROL_BYTE + details, protocol=FileSharingProtocol.FILE_PROTOCOL)
                elif status == "SEND_SUCCESS":
                    msg = f"File received successfully: {self.receiver.filename}"
                    print(msg)
                    screen_reader.speak(msg)
                    delayed_send(self.gw, FileSharingProtocol.CONTROL_BYTE + FileSharingProtocol.SUCCESS_SIGNAL, protocol=FileSharingProtocol.FILE_PROTOCOL)
                elif status == "SEND_NACK":
                    nack_msg = FileSharingProtocol.NACK_PREFIX + ",".join(map(str, details)).encode()
                    delayed_send(self.gw, FileSharingProtocol.CONTROL_BYTE + nack_msg, protocol=FileSharingProtocol.FILE_PROTOCOL)
                return

        self.data = text
        print(self.data)
        screen_reader.speak(self.data)

    def parse(self):
        """
        Parse stored data for URLs, emails, and phone numbers.

        Returns:
            dict: Dictionary with 'urls', 'emails', and 'phones' keys
        """
        return parse.extract_info(self.data)

# Global app state components
output = None
g = None
validator = CommandValidator()


# Define commands using decorators
@validator.command("p")
@validator.integer("protocol_number", minimum=0, maximum=11)
@validator.integer("payload_length",
                   required=False,
                   minimum=4, maximum=64,
                   default=None)
def handle_protocol_command(parsed):
    """Set protocol and payload length. Payload length is optional and must be between 4 and 64. For protocols 9-11, it defaults to 32 if not specified."""
    g.protocol = parsed.protocol_number
    settings.set("protocol", g.protocol)
    toreturn = f"protocol set to {g.protocol}. "

    payload = parsed.payload_length
    if payload is None and g.protocol >= 9:
        payload = 32

    if payload is not None:
        g.switchinstance(payload)
        settings.set("payload_length", payload)
        return toreturn + f"payload length {payload}"
    else:
        g.switchinstance(-1)
        settings.set("payload_length", -1)
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
    settings.set("devices", [-1, -1])
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

    # Protocol check: Send RPC if not already on the file sending protocol
    if g.protocol != FileSharingProtocol.FILE_PROTOCOL:
        print(f"Switching remote protocol to {FileSharingProtocol.FILE_PROTOCOL}...")
        cmd = f"__RPC__:{FileSharingProtocol.FILE_PROTOCOL}:-1"
        g.send(cmd)
        time.sleep(0.5) # SAR delay

    print(f"Starting handshake for {sender.filename}...")
    g.send(sender.get_handshake_data(), protocol=FileSharingProtocol.FILE_PROTOCOL)
    sender.state = "WAITING_FOR_READY"

    # Wait for ready signal
    start_time = time.time()
    while sender.state == "WAITING_FOR_READY" and time.time() - start_time < 30:
        time.sleep(0.1)

    if sender.state == "WAITING_FOR_READY":
        output.sender = None
        return "Handshake timeout (30s). Make sure the receiver is listening."

    print("Handshake successful, sending chunks...")
    # send_all_chunks was handled in data_callback

    # Wait for completion or retransmission requests
    start_time = time.time()
    while sender.state != "DONE" and time.time() - start_time < 120: # Increased timeout for larger files
        time.sleep(0.1)

    if sender.state == "DONE":
        output.sender = None
        return f"File {sender.filename} sent successfully."
    else:
        output.sender = None
        return f"File transfer timed out or failed. State: {sender.state}"

@validator.command("newplugin")
@validator.string("name")
def handle_newplugin_command(parsed):
    """Create a new plugin template. Usage: /newplugin <name>"""
    success, msg = command_manager.create_plugin_template(parsed.name)
    return msg

@validator.command("refresh")
def handle_refresh_command(parsed):
    """Refresh local plugins list"""
    command_manager.load_plugins()
    return "Plugins reloaded."

@validator.command("query")
def handle_query_command(parsed):
    """Query remote device for its available commands"""
    print("Querying remote device for functions...")
    g.send("__QUERY_REMOTE__")
    output.query_last_received = time.time()
    output.query_active = True
    output.query_functions = []
    return "Query sent."

@validator.command("remote")
@validator.string("cmd_name")
@validator.string("args", default="")
def handle_remote_command(parsed):
    """Execute a remote command. Usage: /remote <cmd_name> [args]"""
    cmd = f"__REMOTE__:{parsed.cmd_name}:{parsed.args}"
    g.send(cmd)
    return f"Sent remote command: {parsed.cmd_name} {parsed.args}"


def command(cmd):
    """Process a command or message"""
    if not g:
        return "Audio system not initialized"

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
    global g, output
    import configure_sound_devices
    if configure_sound_devices.devs == [-1, -1]:
        configure_sound_devices.test()

    output = Output()
    g = gw.GW(output.data_callback)
    output.gw = g
    output.receiver = FileReceiver(g)
    g.start()

    # Initialize API and command manager
    api = AppAPI(g, print)
    command_manager.set_api(api)

    print("Welcome to data_over_sound")
    print("Type /help for help")
    print("Enter your message or command:")

    import threading
    import queue

    input_queue = queue.Queue()

    def input_thread():
        while True:
            try:
                cmd = input()
                input_queue.put(cmd)
            except EOFError:
                input_queue.put(None)
                break
            except Exception:
                break

    t = threading.Thread(target=input_thread, daemon=True)
    t.start()

    try:
        while True:
            try:
                # Process inputs from queue without blocking
                try:
                    cmd = input_queue.get_nowait()
                    if cmd is None: # EOF
                        break
                    result = command(cmd)
                    if result:
                        print(result)
                except queue.Empty:
                    pass

                # Check for receiver/query timeouts periodically
                status, details = output.receiver.check_timeout()
                if status:
                    if status == "SEND_READY":
                        msg = f"Resending READY for {output.receiver.filename}..."
                        print(msg)
                        delayed_send(g, FileSharingProtocol.CONTROL_BYTE + details, protocol=FileSharingProtocol.FILE_PROTOCOL)
                    elif status == "SEND_NACK":
                        msg = f"Still waiting for chunks of {output.receiver.filename}. Sent NACK."
                        print(msg)
                        screen_reader.speak(msg)
                        nack_msg = FileSharingProtocol.NACK_PREFIX + ",".join(map(str, details)).encode()
                        delayed_send(g, FileSharingProtocol.CONTROL_BYTE + nack_msg, protocol=FileSharingProtocol.FILE_PROTOCOL)
                    elif status == "ABORT":
                        print(details)
                        screen_reader.speak(details)

                if output.query_active:
                    if time.time() - output.query_last_received > 30:
                        output.query_active = False
                        msg = f"Remote query timed out. Received: {', '.join(output.query_functions)}"
                        print(msg)
                        screen_reader.speak(msg)

                time.sleep(0.1)

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
