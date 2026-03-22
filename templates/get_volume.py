from datawave.services.remote_control import BasePlugin

class GetVolumePlugin(BasePlugin):
    """Plugin to retrieve current volume setting."""
    def execute(self, *args):
        vol = self.api.get_setting("volume", 50)
        self.api.log(f"Current volume: {vol}%")
        return f"Volume is {vol}%"
