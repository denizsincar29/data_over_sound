import os
import json
import sys
from typing import Any, Dict, List, Optional

APP_NAME = "DataWave"

def get_appdata_dir() -> str:
    """Get the OS-specific application data directory."""
    if sys.platform == "win32":
        path = os.path.join(os.environ.get("APPDATA", ""), APP_NAME)
    elif sys.platform == "darwin":
        path = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
    else:
        path = os.path.expanduser(f"~/.config/{APP_NAME}")

    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
    return path

class Settings:
    """Singleton class to manage application settings."""
    _instance: Optional['Settings'] = None
    _file_path = os.path.join(get_appdata_dir(), "settings.json")

    def __new__(cls) -> 'Settings':
        if cls._instance is None:
            cls._instance = super(Settings, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self) -> None:
        """Initialize settings with defaults and load from file."""
        self.settings: Dict[str, Any] = {
            "devices": [-1, -1],
            "protocol": 2,
            "payload_length": -1,
            "enable_remote_protocol_change": True,
            "enable_remote_commands": False,
            "hotkeys": {}
        }
        self.load()

    def load(self) -> None:
        """Load settings from the JSON file."""
        # Migrate old DataOverSound settings if they exist
        old_app_name = "DataOverSound"
        if sys.platform == "win32":
            old_path = os.path.join(os.environ.get("APPDATA", ""), old_app_name)
        elif sys.platform == "darwin":
            old_path = os.path.expanduser(f"~/Library/Application Support/{old_app_name}")
        else:
            old_path = os.path.expanduser(f"~/.config/{old_app_name}")

        old_file = os.path.join(old_path, "settings.json")
        if os.path.exists(old_file) and not os.path.exists(self._file_path):
            try:
                with open(old_file, "r") as f:
                    self.settings.update(json.load(f))
                self.save()
            except Exception as e:
                print(f"Error migrating old settings: {e}")

        if os.path.exists(self._file_path):
            try:
                with open(self._file_path, "r") as f:
                    loaded = json.load(f)
                    self.settings.update(loaded)
            except Exception as e:
                print(f"Error loading settings: {e}")

    def save(self) -> None:
        """Save current settings to the JSON file."""
        try:
            with open(self._file_path, "w") as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value by key."""
        return self.settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a setting value and save."""
        self.settings[key] = value
        self.save()

settings = Settings()
