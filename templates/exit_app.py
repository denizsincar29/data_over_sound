import os
from datawave.services.remote_control import BasePlugin

class ExitPlugin(BasePlugin):
    def execute(self, *args):
        self.api.log("Exiting application...")
        os._exit(0)
        return "Exiting..."
