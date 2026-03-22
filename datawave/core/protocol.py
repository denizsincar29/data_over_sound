"""
Unified protocol for DataWave using binary packets.
"""

from enum import IntEnum
from typing import Optional, Tuple, Any, List

class OpCode(IntEnum):
    """Operation codes for DataWave packets."""
    # Control / Remote commands (0x01 - 0x0F)
    QUERY_REMOTE = 0x01
    QUERY_RESPONSE = 0x02
    QUERY_EOF = 0x03
    REMOTE_COMMAND = 0x04
    REMOTE_RPC = 0x05
    QUERY_DENIED = 0x06

    # File sharing commands (0x10 - 0x1F)
    FILE_HANDSHAKE = 0x10
    FILE_READY = 0x11
    FILE_DATA = 0x12
    FILE_NACK = 0x13
    FILE_EOF = 0x14
    FILE_SUCCESS = 0x15

class Packet:
    """Represents a binary packet for DataWave."""
    PREAMBLE = b"\xFF\xFE\xFD"
    HEADER_SIZE = len(PREAMBLE) + 1 # Preamble + OpCode

    def __init__(self, opcode: OpCode, payload: bytes = b""):
        self.opcode = opcode
        self.payload = payload

    def encode(self) -> bytes:
        """Encode packet into binary format."""
        return self.PREAMBLE + bytes([self.opcode]) + self.payload

    @classmethod
    def decode(cls, data: bytes) -> Optional['Packet']:
        """Decode binary format into a packet."""
        if len(data) < cls.HEADER_SIZE:
            return None

        if not data.startswith(cls.PREAMBLE):
            return None

        opcode_val = data[len(cls.PREAMBLE)]
        try:
            opcode = OpCode(opcode_val)
        except ValueError:
            return None

        payload = data[cls.HEADER_SIZE:]
        return cls(opcode, payload)

    def __repr__(self) -> str:
        return f"Packet(opcode={self.opcode.name}, payload_len={len(self.payload)})"
