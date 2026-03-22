"""
Unified Audio Gateway connecting the Audio Engine and Audio Stream.
"""

import threading
import time
import numpy as np
from typing import Optional, Callable, Any
from .audio_engine import AudioEngine
from .audio_stream import AudioStream
from datawave.utils.settings import settings

class Gateway:
    """
    Connects the logic of encoding/decoding with physical audio devices.
    """

    def __init__(self, data_callback: Callable[[bytes], None], **kwargs: Any):
        self.engine = AudioEngine(**kwargs)
        self.data_callback = data_callback
        self.protocol = settings.get("protocol", 2)

        devices = settings.get("devices", [-1, -1])
        input_dev = devices[0] if devices[0] != -1 else None
        output_dev = devices[1] if devices[1] != -1 else None

        self.stream = AudioStream(
            input_device=input_dev,
            output_device=output_dev,
            callback=self._on_audio_input
        )
        self.start()

    def _on_audio_input(self, audio_data: np.ndarray) -> None:
        """Process incoming audio data."""
        decoded = self.engine.decode(bytes(audio_data))
        if decoded:
            try:
                self.data_callback(decoded)
            except Exception as e:
                print(f"Error in data_callback: {e}")

    def send(self, data: bytes, protocol: Optional[int] = None) -> bool:
        """Encode and send data over audio."""
        p_id = protocol if protocol is not None else self.protocol
        waveform = self.engine.encode(data, p_id)
        if waveform is not None:
            self.stream.queue_audio(waveform)
            return True
        return False

    def delayed_send(self, data: bytes, protocol: Optional[int] = None, delay: float = 0.5) -> None:
        """Send data after a specified delay to allow for SAR (Send After Receiving)."""
        def _send():
            time.sleep(delay)
            self.send(data, protocol=protocol)
        threading.Thread(target=_send, daemon=True).start()

    def start(self) -> None:
        """Start the audio stream."""
        self.stream.start()

    def stop(self) -> None:
        """Stop the audio stream."""
        self.stream.stop()

    def reconfigure(self, payload_length: int = -1) -> None:
        """Change the internal ggwave instance configuration."""
        self.engine.reconfigure(payload_length)

    def set_protocol(self, protocol_id: int) -> None:
        """Change the current transmission protocol."""
        self.protocol = protocol_id
        settings.set("protocol", protocol_id)
