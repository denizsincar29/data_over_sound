"""
Simulation environment for testing DataWave protocol logic.
"""

import time
import numpy as np
from typing import Callable, List, Dict
from datawave.core.audio_engine import AudioEngine, FRAMES

class InstanceSimulator:
    """Simulates a single DataWave instance with a loopback or peer connection."""

    def __init__(self, name: str, callback: Callable[[bytes], None]):
        self.name = name
        self.engine = AudioEngine()
        self.callback = callback
        self.peer: 'InstanceSimulator' = None

    def set_peer(self, peer: 'InstanceSimulator') -> None:
        self.peer = peer

    def send(self, data: bytes, protocol: int = 2) -> None:
        """Encode and 'transmit' audio waveform to peer."""
        waveform = self.engine.encode(data, protocol)
        if waveform is not None and self.peer:
            # Simulate transmission of audio chunks
            for i in range(0, len(waveform), FRAMES):
                chunk = waveform[i : i + FRAMES]
                self.peer.receive_audio(chunk.tobytes())

    def receive_audio(self, audio_chunk: bytes) -> None:
        """Decode 'received' audio waveform."""
        decoded = self.engine.decode(audio_chunk)
        if decoded:
            self.callback(decoded)

class NetworkSimulator:
    """Connects two instances for simulated communication."""

    def __init__(self, inst1_cb, inst2_cb):
        self.inst1 = InstanceSimulator("Node A", inst1_cb)
        self.inst2 = InstanceSimulator("Node B", inst2_cb)
        self.inst1.set_peer(self.inst2)
        self.inst2.set_peer(self.inst1)
