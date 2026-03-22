"""
Audio stream management using sounddevice.
"""

import queue
from typing import Optional, Tuple, Callable
import sounddevice as sd
import numpy as np

RATE = 48000
CHANNELS = 1
FRAMES = 1024

class AudioStream:
    """
    Manages the audio input/output stream and queues for transmission.
    """

    def __init__(
        self,
        input_device: Optional[int],
        output_device: Optional[int],
        callback: Callable
    ):
        self.input_device = input_device
        self.output_device = output_device
        self.callback = callback
        self.send_queue: queue.Queue[np.ndarray] = queue.Queue()
        self.stream: Optional[sd.Stream] = None
        self.is_running = False

    def start(self) -> None:
        """Start the audio stream."""
        if self.is_running:
            return

        self.stream = sd.Stream(
            samplerate=RATE,
            blocksize=FRAMES,
            dtype="float32",
            channels=CHANNELS,
            callback=self._audio_callback,
            device=(self.input_device, self.output_device),
        )
        self.stream.start()
        self.is_running = True

    def stop(self) -> None:
        """Stop the audio stream."""
        if not self.is_running or self.stream is None:
            return

        self.stream.stop()
        self.stream.close()
        self.stream = None
        self.is_running = False

    def _audio_callback(
        self,
        indata: np.ndarray,
        outdata: np.ndarray,
        frames: int,
        time: sd.CallbackFlags,
        status: sd.CallbackFlags
    ) -> None:
        """Internal audio callback."""
        is_sending = False
        # Priority: send data if available
        try:
            audio_chunk = self.send_queue.get_nowait()
            outdata[:] = audio_chunk.reshape(outdata.shape)
            is_sending = True
        except queue.Empty:
            outdata[:] = 0

        # Process input data via external callback if not sending (avoid self-hearing)
        if indata is not None and not is_sending:
            self.callback(indata)

    def queue_audio(self, waveform: np.ndarray) -> None:
        """Queue a waveform for transmission."""
        for i in range(0, len(waveform), FRAMES):
            self.send_queue.put(waveform[i : i + FRAMES])
