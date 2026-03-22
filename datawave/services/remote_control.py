"""
Remote command service for the DataWave application.
"""

import os
import sys
import importlib.util
import threading
import time
from typing import Optional, List, Dict, Any, Callable
from datawave.core.protocol import Packet, OpCode
from datawave.utils.settings import settings, get_appdata_dir
from datawave.utils.screen_reader import screen_reader

PLUGINS_DIR = os.path.join(get_appdata_dir(), "plugins")

if not os.path.exists(PLUGINS_DIR):
    os.makedirs(PLUGINS_DIR, exist_ok=True)

class AppAPI:
    """API provided to plugins to interact with the main application."""
    def __init__(self, gateway=None, log_func=None):
        self.gateway = gateway
        self._log_func = log_func

    def speak(self, text: str, interrupt: bool = True) -> None:
        screen_reader.speak(text, interrupt=interrupt)

    def log(self, message: str) -> None:
        if self._log_func:
            self._log_func(message)
        else:
            print(message)

    def send(self, data: bytes) -> None:
        if self.gateway:
            self.gateway.send(data)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return settings.get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        settings.set(key, value)

class BasePlugin:
    """Base class for all plugins."""
    def __init__(self, api: AppAPI):
        self.api = api

    def execute(self, *args: Any) -> Any:
        raise NotImplementedError("Plugins must implement the execute method.")

class RemoteControlService:
    """Manages local and remote command execution."""

    def __init__(self, api: Optional[AppAPI] = None):
        self.api = api or AppAPI()
        self.commands: Dict[str, Callable] = {}
        self.query_active = False
        self.query_functions: List[str] = []
        self.query_last_received = 0.0
        self.load_plugins()

    def set_api(self, api: AppAPI) -> None:
        self.api = api
        self.load_plugins()

    def load_plugins(self) -> None:
        self.commands.clear()

        if not os.path.exists(PLUGINS_DIR):
            return

        for entry in os.listdir(PLUGINS_DIR):
            path = os.path.join(PLUGINS_DIR, entry)
            name = None
            module = None

            if os.path.isfile(path) and entry.endswith(".py") and not entry.startswith("__"):
                name = entry[:-3]
                module = self._load_module(name, path)
            elif os.path.isdir(path):
                init_path = os.path.join(path, "__init__.py")
                if os.path.exists(init_path):
                    name = entry
                    module = self._load_module(name, init_path)

            if module and name:
                self._register_plugin(name, module)

    def _load_module(self, name: str, path: str) -> Optional[Any]:
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module
                spec.loader.exec_module(module)
                return module
        except Exception as e:
            print(f"Error loading plugin {name}: {e}")
        return None

    def _register_plugin(self, name: str, module: Any) -> None:
        found_class = False
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and issubclass(attr, BasePlugin)
                and attr is not BasePlugin):
                try:
                    plugin_instance = attr(self.api)
                    self.commands[name] = plugin_instance.execute
                    found_class = True
                    break
                except Exception as e:
                    print(f"Error instantiating plugin {name}: {e}")

        if not found_class and hasattr(module, "execute"):
            self.commands[name] = module.execute

    def execute_local(self, cmd_name: str, *args: Any) -> Any:
        if cmd_name in self.commands:
            try:
                return self.commands[cmd_name](*args)
            except Exception as e:
                return f"Error executing {cmd_name}: {e}"
        return f"Command {cmd_name} not found"

    def handle_packet(self, packet: Packet, gateway: Any) -> Optional[str]:
        """Process remote control packets."""
        if packet.opcode == OpCode.QUERY_REMOTE:
            if not settings.get("enable_remote_commands", False):
                def deny():
                    time.sleep(settings.get("sar_delay", 500) / 1000.0)
                    gateway.send(Packet(OpCode.QUERY_DENIED, b"nah i dont allow remote!").encode())
                threading.Thread(target=deny, daemon=True).start()
                return "Remote query denied (disabled in settings)."

            def respond():
                sar_delay = settings.get("sar_delay", 500) / 1000.0
                sub_delay = settings.get("subsequent_delay", 100) / 1000.0
                time.sleep(sar_delay)
                for name in self.commands.keys():
                    gateway.send(Packet(OpCode.QUERY_RESPONSE, name.encode()).encode())
                    time.sleep(sub_delay)
                gateway.send(Packet(OpCode.QUERY_EOF).encode())

            threading.Thread(target=respond, daemon=True).start()
            return "Responding to remote query..."

        elif packet.opcode == OpCode.QUERY_RESPONSE:
            if self.query_active:
                name = packet.payload.decode()
                self.query_functions.append(name)
                self.query_last_received = time.time()
                return f"Remote function discovered: {name}"

        elif packet.opcode == OpCode.QUERY_EOF:
            if self.query_active:
                self.query_active = False
                return f"Remote query complete. Found: {', '.join(self.query_functions)}"

        elif packet.opcode == OpCode.QUERY_DENIED:
            self.query_active = False
            return f"Remote device denied query: {packet.payload.decode()}"

        elif packet.opcode == OpCode.REMOTE_COMMAND:
            if not settings.get("enable_remote_commands", False):
                return "Remote commands disabled."
            try:
                parts = packet.payload.decode().split(":")
                cmd_name = parts[0]
                args = parts[1:]
                return f"Executing Remote: {cmd_name} {args}. Result: {self.execute_local(cmd_name, *args)}"
            except Exception as e:
                return f"Error parsing remote command: {e}"

        elif packet.opcode == OpCode.REMOTE_RPC:
            try:
                parts = packet.payload.decode().split(":")
                protocol = int(parts[0])
                payload_len = int(parts[1])
                gateway.set_protocol(protocol)
                gateway.reconfigure(payload_len)
                return f"Remote Protocol Change: {protocol} (Payload: {payload_len})"
            except (ValueError, IndexError):
                return "Invalid RPC packet."

        return None

    def create_plugin_template(self, name: str) -> tuple[bool, str]:
        plugin_path = os.path.join(PLUGINS_DIR, name)
        if os.path.exists(plugin_path):
            return False, f"Plugin folder '{name}' already exists."

        try:
            os.makedirs(plugin_path)
            init_content = f"""from datawave.services.remote_control import BasePlugin

class {name.capitalize()}Plugin(BasePlugin):
    def execute(self, *args):
        self.api.speak("Hello from {name}!")
        self.api.log("{name} plugin executed!")
        return "Executed {name}"
"""
            with open(os.path.join(plugin_path, "__init__.py"), "w") as f:
                f.write(init_content)
            self.load_plugins()
            return True, f"Plugin '{name}' created successfully."
        except Exception as e:
            return False, f"Error creating plugin: {e}"

