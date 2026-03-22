"""
Central dispatcher for handling incoming DataWave packets and routing to services.
"""

import os
import time
import threading
import wave
import numpy as np
from typing import Optional, Callable, Any, Dict, List
from datawave.core.protocol import Packet, OpCode
from datawave.core.gateway import Gateway
from datawave.services.file_transfer import FileSender, FileReceiver, FileTransferProtocol
from datawave.services.remote_control import RemoteControlService, AppAPI
from datawave.utils.settings import settings
from datawave.utils.screen_reader import screen_reader

class ProtocolDispatcher:
    """Dispatches incoming data to appropriate handlers (UI, FileTransfer, RemoteControl)."""

    def __init__(self, log_callback: Callable[[str], None], progress_callback: Optional[Callable[[int, int], None]] = None):
        self.log_callback = log_callback
        self.progress_callback = progress_callback

        self.gateway = Gateway(self.data_callback)
        self.remote_control = RemoteControlService(AppAPI(self.gateway, self.log_callback))
        self.file_receiver = FileReceiver()
        self.file_sender: Optional[FileSender] = None

        # UI interaction functions
        self.on_query_complete: Optional[Callable[[List[str]], None]] = None

    def data_callback(self, data: bytes) -> None:
        """Process decoded data from Gateway."""
        packet = Packet.decode(data)

        # If it's a valid packet, handle it through protocol logic
        if packet:
            # 1. Check Remote Control (0x01 - 0x0F)
            if 0x01 <= packet.opcode <= 0x0F:
                result = self.remote_control.handle_packet(packet, self.gateway)
                if result:
                    self.log_callback(result)
                return

            # 2. Check File Transfer (0x10 - 0x1F)
            if 0x10 <= packet.opcode <= 0x1F:
                # Handle sender response
                if self.file_sender and self.file_sender.state != "DONE":
                    action, details = self.file_sender.handle_response(packet)
                    if action == "START_SENDING":
                        self._start_sending_thread()
                        return
                    elif action == "RESEND_CHUNKS":
                        self._resend_chunks_thread(details)
                        return

                # Handle receiver logic
                status, details = self.file_receiver.handle_packet(packet)
                if status:
                    self._handle_receiver_status(status, details)
                return

        # Not a packet (or unknown opcode), treat as raw text
        try:
            text = data.decode("UTF-8").replace("\x00", "")
            self.log_callback(text)
            screen_reader.speak(text)
        except (UnicodeDecodeError, AttributeError):
            self.log_callback(f"Received non-text data: {data.hex()}")

    def _handle_receiver_status(self, status: str, details: Any) -> None:
        """Handle status updates from FileReceiver."""
        sar_delay = settings.get("sar_delay", 500) / 1000.0
        if status == "SEND_READY":
            self.log_callback(f"Receiving file: {self.file_receiver.filename} ({self.file_receiver.num_chunks} chunks)")
            if self.progress_callback:
                self.progress_callback(0, self.file_receiver.num_chunks)
            # Delayed send READY to follow SAR
            self.gateway.delayed_send(Packet(OpCode.FILE_READY).encode(), protocol=FileTransferProtocol.FILE_PROTOCOL_ID, delay=sar_delay)

        elif status == "CHUNK_RECEIVED":
            if self.progress_callback:
                self.progress_callback(len(self.file_receiver.received_chunks), self.file_receiver.num_chunks)

        elif status == "SEND_SUCCESS":
            self.log_callback(f"File received successfully: {self.file_receiver.filename}")
            if self.progress_callback:
                self.progress_callback(self.file_receiver.num_chunks, self.file_receiver.num_chunks)
            self.gateway.delayed_send(Packet(OpCode.FILE_SUCCESS).encode(), protocol=FileTransferProtocol.FILE_PROTOCOL_ID, delay=sar_delay)
            self.file_receiver.reset()

        elif status == "SEND_NACK":
            nack_data = ",".join(map(str, details)).encode()
            self.gateway.delayed_send(Packet(OpCode.FILE_NACK, nack_data).encode(), protocol=FileTransferProtocol.FILE_PROTOCOL_ID, delay=sar_delay)

        elif status == "ERROR" or status == "ABORT":
            self.log_callback(f"File reception error: {details}")

    def _start_sending_thread(self) -> None:
        def send_all():
            if not self.file_sender: return
            sar_delay = settings.get("sar_delay", 500) / 1000.0
            sub_delay = settings.get("subsequent_delay", 100) / 1000.0
            time.sleep(sar_delay)
            for i in range(self.file_sender.num_chunks):
                self.gateway.send(self.file_sender.get_chunk_packet(i).encode(), protocol=FileTransferProtocol.FILE_PROTOCOL_ID)
                time.sleep(sub_delay) # Small delay between chunks to avoid flooding
            self.gateway.send(self.file_sender.get_eof_packet().encode(), protocol=FileTransferProtocol.FILE_PROTOCOL_ID)
        threading.Thread(target=send_all, daemon=True).start()

    def _resend_chunks_thread(self, indices: List[int]) -> None:
        def resend():
            if not self.file_sender: return
            sar_delay = settings.get("sar_delay", 500) / 1000.0
            sub_delay = settings.get("subsequent_delay", 100) / 1000.0
            time.sleep(sar_delay)
            for i in indices:
                self.gateway.send(self.file_sender.get_chunk_packet(i).encode(), protocol=FileTransferProtocol.FILE_PROTOCOL_ID)
                time.sleep(sub_delay)
            self.gateway.send(self.file_sender.get_eof_packet().encode(), protocol=FileTransferProtocol.FILE_PROTOCOL_ID)
        threading.Thread(target=resend, daemon=True).start()

    def send_text(self, text: str) -> None:
        """Send raw text message."""
        self.gateway.send(text.encode())

    def send_file(self, filepath: str) -> None:
        """Initiate file transfer."""
        if not os.path.exists(filepath):
            self.log_callback(f"File not found: {filepath}")
            return

        self.file_sender = FileSender(filepath)

        # Remote protocol check
        if self.gateway.protocol != FileTransferProtocol.FILE_PROTOCOL_ID:
            self.log_callback(f"Switching remote protocol to {FileTransferProtocol.FILE_PROTOCOL_ID}...")
            rpc_data = f"{FileTransferProtocol.FILE_PROTOCOL_ID}:-1".encode()
            self.gateway.send(Packet(OpCode.REMOTE_RPC, rpc_data).encode())

            # Local protocol change
            self.gateway.set_protocol(FileTransferProtocol.FILE_PROTOCOL_ID)
            self.gateway.reconfigure(-1)
            time.sleep(0.5)

        self.log_callback(f"Starting handshake for {self.file_sender.filename}...")
        self.gateway.send(self.file_sender.get_handshake_packet().encode(), protocol=FileTransferProtocol.FILE_PROTOCOL_ID)
        self.file_sender.state = "WAITING_FOR_READY"

    def query_remote(self) -> None:
        """Ask remote device for its functions."""
        self.log_callback("Querying remote device for functions...")
        self.remote_control.query_active = True
        self.remote_control.query_functions = []
        self.remote_control.query_last_received = time.time()
        self.gateway.send(Packet(OpCode.QUERY_REMOTE).encode())

    def send_remote_command(self, cmd_name: str, args: str = "") -> None:
        """Send a command to a remote device."""
        payload = f"{cmd_name}:{args}".encode()
        self.gateway.send(Packet(OpCode.REMOTE_COMMAND, payload).encode())

    def check_timeouts(self) -> None:
        """Periodic timeout check."""
        status, details = self.file_receiver.check_timeout()
        if status:
            self._handle_receiver_status(status, details)

        if self.remote_control.query_active:
            if time.time() - self.remote_control.query_last_received > 30:
                self.remote_control.query_active = False
                self.log_callback(f"Remote query timed out. Received: {', '.join(self.remote_control.query_functions)}")

    def stop(self) -> None:
        """Stop all services and gateway."""
        self.gateway.stop()

    def save_remote_sounds_to_wav(self, output_dir: str = "recs") -> str:
        """Generate and save WAV files for all discovered remote commands."""
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        count = 0
        for cmd_name in self.remote_control.commands:
            payload = f"{cmd_name}:".encode()
            packet = Packet(OpCode.REMOTE_COMMAND, payload)

            # Use normalized 100 volume for exported files
            with threading.Lock(): # Temporary override settings volume
                old_vol = settings.get("volume", 50)
                settings.set("volume", 100)
                waveform = self.gateway.engine.encode(packet.encode(), self.gateway.protocol)
                settings.set("volume", old_vol)

            if waveform is not None:
                filename = os.path.join(output_dir, f"{cmd_name}.wav")
                # Convert float32 to int16 for WAV
                int_wf = (waveform * 32767).astype(np.int16)
                with wave.open(filename, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(48000)
                    wf.writeframes(int_wf.tobytes())
                count += 1

        return f"Saved {count} remote command sounds to {output_dir}/"
