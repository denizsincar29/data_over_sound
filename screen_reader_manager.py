from accessible_output3 import speech

class ScreenReader:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ScreenReader, cls).__new__(cls)
            try:
                cls._instance.speaker = speech.Speaker()
            except Exception:
                cls._instance.speaker = None
        return cls._instance

    def speak(self, text, interrupt=True):
        if self.speaker:
            try:
                self.speaker.speak(text, interrupt=interrupt)
            except Exception:
                pass

screen_reader = ScreenReader()
