"""
Audio data transmission module using ggwave library.

This module provides the GW class for sending and receiving data over sound waves.
"""

import configure_sound_devices
import time
import threading
from queue import Queue, Empty
from threading import Lock, Event
import numpy as np
import ggwave
import sounddevice as sd
from settings_manager import settings
from typing import Optional

ggwave.disableLog()

# Configuration constants
RATE = 48000
CHANNELS = 1
FRAMES = 1024


def delayed_send(gw_instance: "GW", data: bytes, protocol: Optional[int] = None, delay: float = 0.5) -> None:
    """
    Sends data after a delay in a separate thread to avoid blocking.

    Args:
        gw_instance: The audio gateway instance.
        data: The data to send.
        protocol: The protocol ID to use.
        delay: Delay in seconds.
    """
    def _send():
        time.sleep(delay)
        gw_instance.send(data, protocol=protocol)
    threading.Thread(target=_send, daemon=True).start()


class GW:
    """
    GW (GGWave) class for audio data transmission.
    
    Handles encoding/decoding data to/from audio using the ggwave library.
    Thread-safe for use in audio callback contexts.
    """
    
    def __init__(self, callback_function, **kwargs):
        """
        Initialize GW instance.
        
        Args:
            callback_function: Function to call when data is received
            **kwargs: Additional parameters to pass to ggwave
        """
        self.sendqueue = Queue()
        self.callback_function = callback_function
        self.protocol = settings.get("protocol", 2)
        
        # Thread synchronization
        self._instance_lock = Lock()
        self._stop_event = Event()
        
        # Initialize ggwave
        self.pars = ggwave.getDefaultParameters()
        for k, v in kwargs.items():
            self.pars[k] = v
        self.instance = ggwave.init(self.pars)
        
        # Initialize audio stream
        devices = configure_sound_devices.devs
        input_device = devices[0] if devices[0] != -1 else None
        output_device = devices[1] if devices[1] != -1 else None

        self.stream = sd.Stream(
            samplerate=RATE,
            blocksize=FRAMES,
            dtype="float32",
            channels=CHANNELS,
            callback=self.callback,
            device=(input_device, output_device),
        )
        self.started = False
        self.start()

    def callback(self, indata, outdata, frames, time, status):
        """
        Audio callback function called by sounddevice in audio thread.
        
        This method is thread-safe and handles both sending and receiving.
        """
        # Check for stop condition
        if self._stop_event.is_set():
            self._stop_event.clear()
            outdata[:] = 0
            return
        
        # Priority: send data if available
        try:
            audio_chunk = self.sendqueue.get_nowait()
            outdata[:] = audio_chunk.reshape(outdata.shape)
            return
        except Empty:
            pass
        
        # No data to send, output silence
        outdata[:] = 0
        
        # Try to receive data
        with self._instance_lock:
            res = ggwave.decode(self.instance, bytes(indata))
        
        if res is not None:
            # Call user callback (note: this is called from audio thread)
            try:
                self.callback_function(res)
            except Exception as e:
                # Don't let user callback errors crash the audio thread
                print(f"Warning: callback_function raised exception: {e}")

    def start(self):
        """Start the audio stream."""
        if self.started:
            return
        self.started = True
        self.stream.start()

    def stop(self):
        """Stop the audio stream and clean up resources."""
        if not self.started:
            return
        self.started = False
        self.stream.stop()
        self.stream.close()

    def send(self, data, protocol=None):
        """
        Encode and queue data for transmission.
        
        Args:
            data: String or bytes to transmit over audio
            protocol: Optional protocolId to override default protocol
        """
        with self._instance_lock:
            p_id = protocol if protocol is not None else self.protocol
            encoded = ggwave.encode(data, protocolId=p_id, instance=self.instance)
            if not encoded:
                return

            wf = np.frombuffer(
                encoded,
                dtype="float32",
            )
        
        # Ensure the waveform is a multiple of FRAMES by padding with zeros
        remainder = len(wf) % FRAMES
        if remainder > 0:
            padding = FRAMES - remainder
            wf = np.concatenate([wf, np.zeros(padding, dtype="float32")])

        # Split audio into chunks and queue for transmission
        for i in range(0, len(wf), FRAMES):
            self.sendqueue.put(wf[i : i + FRAMES])

    def switchinstance(self, payload_length=-1):
        """
        Reinitialize ggwave instance with new payload length.
        
        Args:
            payload_length: Payload length in bytes. Use -1 for default.
        """
        with self._instance_lock:
            ggwave.free(self.instance)
            if payload_length != -1:
                self.pars["payloadLength"] = payload_length
            else:
                # Reset to default by removing the key
                self.pars.pop("payloadLength", None)
            self.instance = ggwave.init(self.pars)

    def __del__(self):
        """Cleanup ggwave instance and audio stream on deletion."""
        try:
            if self.started:
                self.stop()
            with self._instance_lock:
                if hasattr(self, 'instance') and self.instance:
                    ggwave.free(self.instance)
        except Exception:
            # Ignore errors during cleanup
            pass


def try_to_utf8(val):
    """
    Try to decode bytes to UTF-8 string.
    
    Args:
        val: Bytes to decode
        
    Returns:
        Decoded string or original value if decoding fails
    """
    try:
        return val.decode("UTF-8").replace("\x00", "")
    except (UnicodeDecodeError, AttributeError):
        return val
