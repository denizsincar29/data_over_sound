"""
File transfer service for the DataWave application.
"""

import os
import hashlib
import time
from typing import Optional, List, Dict, Any, Tuple
from datawave.core.protocol import Packet, OpCode
from datawave.utils.settings import settings

class FileTransferProtocol:
    """Constants and utilities for file sharing."""
    FILE_PROTOCOL_ID = 2
    CHUNK_SIZE = 130  # Leave room for 4-byte header

    @staticmethod
    def get_hash(data: bytes) -> str:
        """Calculate MD5 hash of data."""
        return hashlib.md5(data).hexdigest()

class FileSender:
    """Handles the transmission side of file transfer."""
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            self.data = f.read()
        self.hash = FileTransferProtocol.get_hash(self.data)
        self.chunks = [self.data[i : i + FileTransferProtocol.CHUNK_SIZE]
                       for i in range(0, len(self.data), FileTransferProtocol.CHUNK_SIZE)]
        self.num_chunks = len(self.chunks)
        self.state = "IDLE"

    def get_handshake_packet(self) -> Packet:
        """Generate handshake packet."""
        handshake_data = f"{self.filename}|{self.num_chunks}|{self.hash}".encode()
        return Packet(OpCode.FILE_HANDSHAKE, handshake_data)

    def handle_response(self, packet: Packet) -> Tuple[Optional[str], Any]:
        """Process response packets and return (action, details)."""
        if packet.opcode == OpCode.FILE_READY:
            if self.state == "WAITING_FOR_READY":
                self.state = "SENDING_CHUNKS"
                return ("START_SENDING", None)
        elif packet.opcode == OpCode.FILE_SUCCESS:
            if self.state in ["SENDING_CHUNKS", "WAITING_FOR_ACK"]:
                self.state = "DONE"
                return ("COMPLETED", None)
        elif packet.opcode == OpCode.FILE_NACK:
            if self.state in ["SENDING_CHUNKS", "WAITING_FOR_ACK"]:
                try:
                    indices_str = packet.payload.decode()
                    indices = [int(i) for i in indices_str.split(",") if i.strip()]
                    self.state = "WAITING_FOR_ACK"
                    return ("RESEND_CHUNKS", indices)
                except (ValueError, UnicodeDecodeError):
                    pass
        return (None, None)

    def get_chunk_packet(self, index: int) -> Packet:
        """Generate data chunk packet."""
        header = index.to_bytes(2, byteorder='big')
        return Packet(OpCode.FILE_DATA, header + self.chunks[index])

    def get_eof_packet(self) -> Packet:
        """Generate EOF packet."""
        return Packet(OpCode.FILE_EOF)

class FileReceiver:
    """Handles the reception side of file transfer."""
    def __init__(self, save_dir: str = "files"):
        self.save_dir = save_dir
        if not os.path.exists(save_dir):
            os.makedirs(save_dir, exist_ok=True)
        self.reset()

    def reset(self) -> None:
        """Reset receiver state."""
        self.filename: Optional[str] = None
        self.num_chunks = 0
        self.expected_hash: Optional[str] = None
        self.received_chunks: Dict[int, bytes] = {}
        self.state = "IDLE"
        self.last_activity = 0.0
        self.ready_sent_count = 0
        self.eof_received = False

    def handle_packet(self, packet: Packet) -> Tuple[Optional[str], Any]:
        """Process received packets and return (status, details)."""
        if packet.opcode == OpCode.FILE_HANDSHAKE:
            try:
                info = packet.payload.decode().split("|")
                self.filename = info[0]
                self.num_chunks = int(info[1])
                self.expected_hash = info[2]
                self.received_chunks = {}
                self.state = "RECEIVING"
                self.last_activity = time.time()
                self.ready_sent_count = 1
                self.eof_received = False
                return ("SEND_READY", None)
            except (IndexError, ValueError, UnicodeDecodeError):
                return ("ERROR", "Invalid Handshake.")

        if self.state == "RECEIVING":
            if packet.opcode == OpCode.FILE_EOF:
                self.eof_received = True
                self.last_activity = time.time()
                return self.check_completion()

            elif packet.opcode == OpCode.FILE_HANDSHAKE:
                # Re-sent handshake, just ignore or re-send READY
                return ("SEND_READY", None)

            elif packet.opcode == OpCode.FILE_DATA:
                payload = packet.payload
                if len(payload) >= 2:
                    try:
                        index = int.from_bytes(payload[:2], byteorder='big')
                        chunk_data = payload[2:]
                        if 0 <= index < self.num_chunks:
                            if index not in self.received_chunks:
                                self.received_chunks[index] = chunk_data
                            self.last_activity = time.time()
                            if len(self.received_chunks) == self.num_chunks:
                                return self.check_completion()
                            return ("CHUNK_RECEIVED", index)
                    except (ValueError, TypeError):
                        pass
        return (None, None)

    def check_timeout(self) -> Tuple[Optional[str], Any]:
        """Check for transfer timeouts."""
        if self.state == "RECEIVING" and self.num_chunks > 0:
            timeout = 15
            if time.time() - self.last_activity > timeout:
                if len(self.received_chunks) == 0 and not self.eof_received:
                    if self.ready_sent_count < 3:
                        self.ready_sent_count += 1
                        self.last_activity = time.time()
                        return ("SEND_READY", None)
                    else:
                        msg = f"Handshake timeout for {self.filename}."
                        self.reset()
                        return ("ABORT", msg)
                else:
                    missing = [i for i in range(self.num_chunks) if i not in self.received_chunks]
                    if missing:
                        self.last_activity = time.time()
                        return ("SEND_NACK", missing)
        return (None, None)

    def check_completion(self) -> Tuple[Optional[str], Any]:
        """Verify completion and hash."""
        if len(self.received_chunks) == self.num_chunks:
            all_data = b"".join(self.received_chunks[i] for i in range(self.num_chunks))
            if FileTransferProtocol.get_hash(all_data) == self.expected_hash:
                safe_filename = os.path.basename(self.filename or "received_file")
                filepath = os.path.join(self.save_dir, safe_filename)
                with open(filepath, "wb") as f:
                    f.write(all_data)
                self.state = "DONE"
                return ("SEND_SUCCESS", self.filename)
            else:
                return ("ERROR", "Hash Mismatch.")
        elif self.eof_received:
            missing = [i for i in range(self.num_chunks) if i not in self.received_chunks]
            return ("SEND_NACK", missing)
        return (None, None)
