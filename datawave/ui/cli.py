"""
CLI entry point for DataWave.
"""

import os
import sys
import time
import threading
import queue
from datawave.core.dispatcher import ProtocolDispatcher
from datawave.utils.settings import settings
from datawave.utils.parser import extract_info
from webbrowser import open as wopen

class DataWaveCLI:
    def __init__(self):
        self.dispatcher = ProtocolDispatcher(self.log)
        self.input_queue = queue.Queue()

    def log(self, message: str) -> None:
        """Log message to console."""
        print(f"\r{message}\n> ", end="", flush=True)

    def _input_thread(self) -> None:
        """Thread for reading user input."""
        while True:
            try:
                cmd = input("> ")
                self.input_queue.put(cmd)
            except EOFError:
                self.input_queue.put(None)
                break
            except Exception:
                break

    def run(self) -> None:
        """Main application loop."""
        print("Welcome to DataWave")
        print("Type /help for commands")

        t = threading.Thread(target=self._input_thread, daemon=True)
        t.start()

        try:
            while True:
                try:
                    cmd = self.input_queue.get(timeout=1.0)
                    if cmd is None: break
                    self.process_command(cmd)
                except queue.Empty:
                    pass

                # Check for dispatcher timeouts
                self.dispatcher.check_timeouts()

        except KeyboardInterrupt:
            print("\nExiting...")
        finally:
            self.dispatcher.stop()

    def process_command(self, cmd: str) -> None:
        if not cmd.strip(): return

        if cmd.startswith("/"):
            parts = cmd[1:].split(" ")
            action = parts[0].lower()
            args = parts[1:]

            if action == "help":
                print("/help - Show help")
                print("/sendfile <path> - Send a file")
                print("/query - Query remote functions")
                print("/remote <name> [args] - Execute remote command")
                print("/protocol <num> [len] - Set protocol and payload length")
                print("/open - Open received links/emails/phones")
                print("/exit - Exit")
            elif action == "sendfile" and args:
                self.dispatcher.send_file(args[0])
            elif action == "query":
                self.dispatcher.query_remote()
            elif action == "remote" and args:
                self.dispatcher.send_remote_command(args[0], " ".join(args[1:]))
            elif action == "protocol" and args:
                p_id = int(args[0])
                p_len = int(args[1]) if len(args) > 1 else -1
                self.dispatcher.gateway.set_protocol(p_id)
                self.dispatcher.gateway.reconfigure(p_len)
                print(f"Protocol set to {p_id} (Payload: {p_len})")
            elif action == "open":
                self._handle_open()
            elif action == "exit":
                self.dispatcher.stop()
                sys.exit(0)
            else:
                print(f"Unknown command: {action}")
        else:
            self.dispatcher.send_text(cmd)

    def _handle_open(self) -> None:
        # Note: In a real app, you'd want to track the *last* received text.
        # This is a simplification.
        pass

def main():
    cli = DataWaveCLI()
    cli.run()

if __name__ == "__main__":
    main()
