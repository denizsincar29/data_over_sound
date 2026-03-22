from webbrowser import open as wopen
from datawave.services.remote_control import BasePlugin

class PlayMusicPlugin(BasePlugin):
    def execute(self, *args):
        self.api.log("Opening music results...")
        wopen("https://www.youtube.com/results?search_query=music")
        return "Playing music..."
