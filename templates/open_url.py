from webbrowser import open as wopen
from datawave.services.remote_control import BasePlugin

class OpenUrlPlugin(BasePlugin):
    def execute(self, url=None, *args):
        if url:
            self.api.log(f"Opening URL: {url}")
            wopen(url)
            return f"Opening {url}"
        return "No URL provided"
