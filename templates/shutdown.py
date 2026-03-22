import os
import sys
from datawave.services.remote_control import BasePlugin

class ShutdownPlugin(BasePlugin):
    def execute(self, *args):
        self.api.log("Shutting down...")
        if sys.platform == "win32":
            os.system("shutdown /s /t 1")
        else:
            os.system("shutdown -h now")
        return "Shutting down..."
