"""
Core audio engine using the ggwave library for encoding and decoding.
"""

import threading
from threading import Lock
import numpy as np
import ggwave
from typing import Optional, Callable, Dict, Any

# Initial configuration constants
RATE = 48000
CHANNELS = 1
FRAMES = 1024

class AudioEngine:
    """
    Handles encoding and decoding of data to/from audio using ggwave.
    Does not manage audio devices directly.
    """

    def __init__(self, **kwargs: Any):
        """
        Initialize the ggwave instance.
        """
        ggwave.disableLog()
        self._instance_lock = Lock()
        self.pars = ggwave.getDefaultParameters()
        for k, v in kwargs.items():
            self.pars[k] = v

        with self._instance_lock:
            self.instance = ggwave.init(self.pars)

    def encode(self, data: bytes, protocol_id: int) -> Optional[np.ndarray]:
        """
        Encode bytes into a floating-point audio waveform.
        """
        with self._instance_lock:
            encoded = ggwave.encode(data, protocolId=protocol_id, instance=self.instance)
            if not encoded:
                return None

            wf = np.frombuffer(encoded, dtype="float32")

        # Ensure the waveform is a multiple of FRAMES by padding with zeros
        remainder = len(wf) % FRAMES
        if remainder > 0:
            padding = FRAMES - remainder
            wf = np.concatenate([wf, np.zeros(padding, dtype="float32")])

        return wf

    def decode(self, audio_data: bytes) -> Optional[bytes]:
        """
        Decode bytes from an audio waveform.
        """
        with self._instance_lock:
            return ggwave.decode(self.instance, audio_data)

    def reconfigure(self, payload_length: int = -1) -> None:
        """
        Reinitialize the ggwave instance with a new payload length.
        """
        with self._instance_lock:
            if hasattr(self, 'instance') and self.instance:
                ggwave.free(self.instance)

            if payload_length != -1:
                self.pars["payloadLength"] = payload_length
            else:
                self.pars.pop("payloadLength", None)

            self.instance = ggwave.init(self.pars)

    def __del__(self) -> None:
        """Free ggwave resources."""
        try:
            with self._instance_lock:
                if hasattr(self, 'instance') and self.instance:
                    ggwave.free(self.instance)
        except Exception:
            pass
