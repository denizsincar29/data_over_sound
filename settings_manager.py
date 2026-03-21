import os
import json
import sys

APP_NAME = "DataOverSound"

def get_appdata_dir():
    if sys.platform == "win32":
        path = os.path.join(os.environ["APPDATA"], APP_NAME)
    elif sys.platform == "darwin":
        path = os.path.expanduser(os.path.join("~/Library/Application Support", APP_NAME))
    else:
        path = os.path.expanduser(os.path.join("~/.config", APP_NAME))

    if not os.path.exists(path):
        os.makedirs(path)
    return path

class Settings:
    _instance = None
    _file_path = os.path.join(get_appdata_dir(), "settings.json")

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Settings, cls).__new__(cls)
            cls._instance.load()
        return cls._instance

    def load(self):
        self.settings = {
            "devices": [-1, -1],
            "protocol": 2,
            "payload_length": -1,
            "enable_remote_protocol_change": True,
            "enable_remote_commands": False,
            "hotkeys": {}
        }

        # Check if old devices.json exists and migrate it
        if os.path.exists("devices.json"):
            try:
                with open("devices.json", "r") as f:
                    self.settings["devices"] = json.load(f)
                os.remove("devices.json")
                self.save()
            except Exception as e:
                print(f"Error migrating devices.json: {e}")

        if os.path.exists(self._file_path):
            try:
                with open(self._file_path, "r") as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save(self):
        try:
            with open(self._file_path, "w") as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get(self, key, default=None):
        return self.settings.get(key, default)

    def set(self, key, value):
        self.settings[key] = value
        self.save()

settings = Settings()
