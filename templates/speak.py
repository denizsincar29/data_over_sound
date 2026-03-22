from datawave.services.remote_control import BasePlugin

class SpeakPlugin(BasePlugin):
    """Plugin to speak text using the accessibility engine."""
    def execute(self, text="Hello from DataWave!", *args):
        self.api.speak(text)
        self.api.log(f"Spoke: {text}")
        return f"Spoke: {text}"
