import os
import hashlib
import time

class FileSharingProtocol:
    HANDSHAKE_PREFIX = b"FS_START:"
    READY_SIGNAL = b"FS_READY"
    SUCCESS_SIGNAL = b"FS_SUCCESS"
    NACK_PREFIX = b"FS_NACK:"
    EOF_SIGNAL = b"FS_EOF"

    # Prefixes to distinguish control from data
    CONTROL_BYTE = b"\x00"
    DATA_BYTE = b"\x01"

    # Use Audible Fast (Protocol 2) for file transfer for best speed/reliability.
    # Audible protocols use variable length payloads (up to 140 bytes).
    FILE_PROTOCOL = 2
    CHUNK_SIZE = 137  # 1 byte prefix + 2 bytes index + 137 bytes data = 140 bytes

    @staticmethod
    def get_hash(data):
        return hashlib.md5(data).hexdigest()

class FileSender:
    def __init__(self, gw, filepath):
        self.gw = gw
        self.filepath = filepath
        self.filename = os.path.basename(filepath)
        with open(filepath, "rb") as f:
            self.data = f.read()
        self.hash = FileSharingProtocol.get_hash(self.data)
        self.chunks = []
        for i in range(0, len(self.data), FileSharingProtocol.CHUNK_SIZE):
            self.chunks.append(self.data[i : i + FileSharingProtocol.CHUNK_SIZE])
        self.num_chunks = len(self.chunks)
        self.state = "IDLE"

    def get_handshake_data(self):
        # Even with variable length, we should limit filename to keep handshake under 140 bytes.
        limit = 138 - len(FileSharingProtocol.HANDSHAKE_PREFIX) - len(str(self.num_chunks)) - len(self.hash) - 2
        safe_filename = self.filename
        if len(safe_filename) > limit:
            name, ext = os.path.splitext(self.filename)
            safe_filename = name[:limit-len(ext)] + ext

        handshake = f"{safe_filename}|{self.num_chunks}|{self.hash}".encode()
        return FileSharingProtocol.CONTROL_BYTE + FileSharingProtocol.HANDSHAKE_PREFIX + handshake

    def handle_response(self, data):
        """
        Processes received data and returns a tuple (action, details)
        Actions:
            - 'START_SENDING': Handshake accepted, start sending chunks
            - 'RESEND_CHUNKS': NACK received, details is list of indices
            - 'COMPLETED': Success signal received
            - None: No action needed or irrelevant data
        """
        if not data.startswith(FileSharingProtocol.CONTROL_BYTE):
            return (None, None)

        response = data[1:]

        if self.state == "WAITING_FOR_READY" and response == FileSharingProtocol.READY_SIGNAL:
            self.state = "SENDING_CHUNKS"
            return ("START_SENDING", None)

        elif self.state in ["SENDING_CHUNKS", "WAITING_FOR_ACK"]:
            if response == FileSharingProtocol.SUCCESS_SIGNAL:
                self.state = "DONE"
                return ("COMPLETED", None)
            elif response.startswith(FileSharingProtocol.NACK_PREFIX):
                try:
                    indices_str = response[len(FileSharingProtocol.NACK_PREFIX):].decode()
                    indices = [int(i) for i in indices_str.split(",") if i.strip()]
                    self.state = "WAITING_FOR_ACK"
                    return ("RESEND_CHUNKS", indices)
                except Exception:
                    return (None, None)
        return (None, None)

    def get_chunk_data(self, index):
        header = index.to_bytes(2, byteorder='big')
        return FileSharingProtocol.DATA_BYTE + header + self.chunks[index]

    def get_eof_data(self):
        return FileSharingProtocol.CONTROL_BYTE + FileSharingProtocol.EOF_SIGNAL

class FileReceiver:
    def __init__(self, gw, save_dir="files"):
        self.gw = gw
        self.save_dir = save_dir
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        self.reset()

    def reset(self):
        self.filename = None
        self.num_chunks = 0
        self.expected_hash = None
        self.received_chunks = {}
        self.state = "IDLE"
        self.last_activity = 0
        self.ready_sent_count = 0
        self.eof_received = False

    def handle_data(self, data):
        """
        Processes received data and returns a tuple (status, details)
        Statuses:
            - 'HANDSHAKE_RECEIVED': New file transfer initiated
            - 'CHUNK_RECEIVED': A file chunk was received
            - 'SUCCESS': File transfer completed successfully
            - 'ERROR': Something went wrong
            - 'SEND_READY': Need to send READY signal
            - 'SEND_NACK': Need to send NACK for missing chunks
            - None: No status change
        """
        if data.startswith(FileSharingProtocol.CONTROL_BYTE):
            control_data = data[1:]
            if control_data.startswith(FileSharingProtocol.HANDSHAKE_PREFIX):
                try:
                    info = control_data[len(FileSharingProtocol.HANDSHAKE_PREFIX):].decode().split("|")
                    self.filename = info[0]
                    self.num_chunks = int(info[1])
                    self.expected_hash = info[2]
                    self.received_chunks = {}
                    self.state = "RECEIVING"
                    self.last_activity = time.time()
                    self.ready_sent_count = 1
                    self.eof_received = False
                    return ("SEND_READY", FileSharingProtocol.READY_SIGNAL)
                except Exception:
                    return ("ERROR", "Invalid handshake")

            if self.state == "RECEIVING":
                if control_data == FileSharingProtocol.EOF_SIGNAL:
                    self.eof_received = True
                    self.last_activity = time.time()
                    return self.check_completion()

        elif data.startswith(FileSharingProtocol.DATA_BYTE):
            if self.state == "RECEIVING":
                chunk_payload = data[1:]
                if len(chunk_payload) >= 2:
                    try:
                        index = int.from_bytes(chunk_payload[:2], byteorder='big')
                        chunk_data = chunk_payload[2:]
                        if 0 <= index < self.num_chunks:
                            if index not in self.received_chunks:
                                self.received_chunks[index] = chunk_data
                            self.last_activity = time.time()

                            if len(self.received_chunks) == self.num_chunks:
                                return self.check_completion()
                            return ("CHUNK_RECEIVED", index)
                    except Exception:
                        pass
        return (None, None)

    def check_timeout(self):
        """
        Checks for timeouts and returns (action, details) if something needs to be sent.
        Actions:
            - 'SEND_READY': Resend READY signal
            - 'SEND_NACK': Send NACK for missing chunks
            - 'ABORT': Too many retries, give up
            - None: No action
        """
        if self.state == "RECEIVING" and self.num_chunks > 0:
            timeout = 15
            if time.time() - self.last_activity > timeout:
                if len(self.received_chunks) == 0 and not self.eof_received:
                    if self.ready_sent_count < 3:
                        self.ready_sent_count += 1
                        self.last_activity = time.time()
                        return ("SEND_READY", FileSharingProtocol.READY_SIGNAL)
                    else:
                        msg = f"Handshake timeout for {self.filename} after 3 attempts"
                        self.reset()
                        return ("ABORT", msg)
                else:
                    # We have some chunks or EOF, but not all chunks
                    missing = [i for i in range(self.num_chunks) if i not in self.received_chunks]
                    if missing:
                        self.last_activity = time.time() # Reset to avoid spamming
                        return ("SEND_NACK", missing)
        return (None, None)

    def check_completion(self):
        if len(self.received_chunks) == self.num_chunks:
            all_data = b""
            for i in range(self.num_chunks):
                all_data += self.received_chunks[i]

            actual_hash = FileSharingProtocol.get_hash(all_data)
            if actual_hash == self.expected_hash:
                # Sanitize filename to prevent path traversal
                safe_filename = os.path.basename(self.filename)
                filepath = os.path.join(self.save_dir, safe_filename)
                with open(filepath, "wb") as f:
                    f.write(all_data)
                self.state = "DONE"
                return ("SEND_SUCCESS", self.filename)
            else:
                return ("ERROR", "Hash mismatch")
        elif self.eof_received:
            # EOF heard but chunks missing, trigger NACK immediately
            missing = [i for i in range(self.num_chunks) if i not in self.received_chunks]
            return ("SEND_NACK", missing)

        return (None, None)

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
