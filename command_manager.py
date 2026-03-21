import os
import sys
import importlib.util
from settings_manager import get_appdata_dir, settings
from screen_reader_manager import screen_reader

PLUGINS_DIR = os.path.join(get_appdata_dir(), "plugins")

if not os.path.exists(PLUGINS_DIR):
    os.makedirs(PLUGINS_DIR)

class AppAPI:
    """API provided to plugins to interact with the main application."""
    def __init__(self, gw_instance=None, log_func=None):
        self.gw = gw_instance
        self._log_func = log_func

    def speak(self, text, interrupt=True):
        """Speak text using the screen reader."""
        screen_reader.speak(text, interrupt=interrupt)

    def log(self, message):
        """Log a message to the application's history/console."""
        if self._log_func:
            self._log_func(message)
        else:
            print(message)

    def send(self, data):
        """Send data over sound."""
        if self.gw:
            self.gw.send(data)

    def get_setting(self, key, default=None):
        """Get an application setting."""
        return settings.get(key, default)

    def set_setting(self, key, value):
        """Set an application setting."""
        settings.set(key, value)

class BasePlugin:
    """Base class for all plugins."""
    def __init__(self, api: AppAPI):
        self.api = api

    def execute(self, *args):
        """Method called when the command is executed."""
        raise NotImplementedError("Plugins must implement the execute method.")

class CommandManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CommandManager, cls).__new__(cls)
            cls._instance.commands = {}
            cls._instance.api = AppAPI()
            cls._instance.load_plugins()
        return cls._instance

    def set_api(self, api: AppAPI):
        """Update the API instance with app-specific handlers."""
        self.api = api
        # Re-initialize plugins with the new API if necessary
        self.load_plugins()

    def load_plugins(self):
        # Default commands
        self.commands["shutdown"] = lambda *args: self._shutdown()
        self.commands["restart"] = lambda *args: self._restart()
        self.commands["exit"] = lambda *args: self._exit_app()
        self.commands["open_url"] = lambda *args: self._open_url(*args)
        self.commands["play_music"] = lambda *args: self._play_music()

        # Load from plugins folder
        if not os.path.exists(PLUGINS_DIR):
            return

        for entry in os.listdir(PLUGINS_DIR):
            path = os.path.join(PLUGINS_DIR, entry)
            module = None
            name = None

            if os.path.isfile(path) and entry.endswith(".py") and not entry.startswith("__"):
                # Single file plugin
                name = entry[:-3]
                module = self._load_module(name, path)
            elif os.path.isdir(path):
                # Folder plugin
                init_path = os.path.join(path, "__init__.py")
                if os.path.exists(init_path):
                    name = entry
                    module = self._load_module(name, init_path)

            if module and name:
                self._register_plugin(name, module)

    def _load_module(self, name, path):
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
            return module
        except Exception as e:
            print(f"Error loading plugin module {name}: {e}")
            return None

    def _register_plugin(self, name, module):
        # Check for BasePlugin subclass
        found_class = False
        for attr_name in dir(module):
            try:
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and issubclass(attr, BasePlugin)
                    and attr is not BasePlugin):
                    try:
                        plugin_instance = attr(self.api)
                        self.commands[name] = plugin_instance.execute
                        found_class = True
                        break
                    except Exception as e:
                        print(f"Error instantiating plugin class {name}: {e}")
            except Exception:
                continue

        if not found_class:
            # Fallback to standalone execute function
            if hasattr(module, "execute"):
                self.commands[name] = module.execute

    def execute(self, cmd_name, *args):
        if cmd_name in self.commands:
            try:
                return self.commands[cmd_name](*args)
            except Exception as e:
                return f"Error executing {cmd_name}: {e}"
        return f"Command {cmd_name} not found"

    def create_plugin_template(self, name):
        """Create a new plugin folder with a template __init__.py."""
        plugin_path = os.path.join(PLUGINS_DIR, name)
        if os.path.exists(plugin_path):
            return False, f"Plugin folder '{name}' already exists."

        try:
            os.makedirs(plugin_path)
            init_content = f"""from command_manager import BasePlugin

class {name.capitalize()}Plugin(BasePlugin):
    def execute(self, *args):
        self.api.speak("Hello World")
        self.api.log("Hello World plugin executed!")
        return "Hello World spoken"
"""
            with open(os.path.join(plugin_path, "__init__.py"), "w") as f:
                f.write(init_content)

            self.load_plugins() # Reload to include the new plugin
            return True, f"Plugin '{name}' created successfully."
        except Exception as e:
            return False, f"Error creating plugin: {e}"

    def get_remote_functions(self):
        """Return a list of available remote command names."""
        return list(self.commands.keys())

    # Default command implementations
    def _shutdown(self):
        if sys.platform == "win32":
            os.system("shutdown /s /t 1")
        else:
            os.system("shutdown -h now")
        return "Shutting down..."

    def _restart(self):
        if sys.platform == "win32":
            os.system("shutdown /r /t 1")
        else:
            os.system("shutdown -r now")
        return "Restarting..."

    def _exit_app(self):
        os._exit(0)
        return "Exiting..."

    def _open_url(self, url):
        from webbrowser import open as wopen
        if url:
            wopen(url)
            return f"Opening {url}"
        return "No URL provided"

    def _play_music(self):
        from webbrowser import open as wopen
        wopen("https://www.youtube.com/results?search_query=music")
        return "Playing music..."

command_manager = CommandManager()
