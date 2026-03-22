"""
Accessibility support via screen reader output.
"""

from typing import Optional, Any
from accessible_output3.outputs.auto import Auto

class ScreenReader:
    """Singleton class to manage screen reader output."""
    _instance: Optional['ScreenReader'] = None

    def __new__(cls) -> 'ScreenReader':
        if cls._instance is None:
            cls._instance = super(ScreenReader, cls).__new__(cls)
            try:
                cls._instance.speaker = Auto()
            except Exception:
                cls._instance.speaker = None
        return cls._instance

    def speak(self, text: str, interrupt: bool = True) -> None:
        """Output text via the system's screen reader."""
        if self.speaker:
            try:
                # Based on memory, call .output(text, interrupt=True)
                self.speaker.output(text, interrupt=interrupt)
            except Exception:
                pass

screen_reader = ScreenReader()
