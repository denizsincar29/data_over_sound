import os
import sys
from datawave.services.remote_control import BasePlugin

class RestartPlugin(BasePlugin):
    def execute(self, *args):
        self.api.log("Restarting...")
        if sys.platform == "win32":
            os.system("shutdown /r /t 1")
        else:
            os.system("shutdown -r now")
        return "Restarting..."
