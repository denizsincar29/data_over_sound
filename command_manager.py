import os
import sys
import importlib.util
from settings_manager import get_appdata_dir

PLUGINS_DIR = os.path.join(get_appdata_dir(), "plugins")

if not os.path.exists(PLUGINS_DIR):
    os.makedirs(PLUGINS_DIR)

class CommandManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CommandManager, cls).__new__(cls)
            cls._instance.commands = {}
            cls._instance.load_plugins()
        return cls._instance

    def load_plugins(self):
        # Default commands
        self.commands["shutdown"] = self._shutdown
        self.commands["restart"] = self._restart
        self.commands["exit"] = self._exit_app
        self.commands["open_url"] = self._open_url
        self.commands["play_music"] = self._play_music

        # Load from plugins folder
        for filename in os.listdir(PLUGINS_DIR):
            if filename.endswith(".py") and not filename.startswith("__"):
                name = filename[:-3]
                path = os.path.join(PLUGINS_DIR, filename)
                try:
                    spec = importlib.util.spec_from_file_location(name, path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    if hasattr(module, "execute"):
                        self.commands[name] = module.execute
                except Exception as e:
                    print(f"Error loading plugin {name}: {e}")

    def execute(self, cmd_name, *args):
        if cmd_name in self.commands:
            try:
                return self.commands[cmd_name](*args)
            except Exception as e:
                return f"Error executing {cmd_name}: {e}"
        return f"Command {cmd_name} not found"

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
        wopen(url)
        return f"Opening {url}"

    def _play_music(self):
        # Example: open a popular music site
        from webbrowser import open as wopen
        wopen("https://www.youtube.com/results?search_query=music")
        return "Playing music..."

command_manager = CommandManager()
