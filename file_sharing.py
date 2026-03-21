import os
import hashlib
import time

class FileSharingProtocol:
    HANDSHAKE_PREFIX = b"FS_START:"
    READY_SIGNAL = b"FS_READY"
    SUCCESS_SIGNAL = b"FS_SUCCESS"
    NACK_PREFIX = b"FS_NACK:"

    CHUNK_SIZE = 64  # Safe size for most ggwave protocols

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

    def send_handshake(self):
        handshake = f"{self.filename}|{self.num_chunks}|{self.hash}".encode()
        self.gw.send(FileSharingProtocol.HANDSHAKE_PREFIX + handshake)
        self.state = "WAITING_FOR_READY"

    def handle_response(self, response):
        if self.state == "WAITING_FOR_READY" and response == FileSharingProtocol.READY_SIGNAL:
            self.send_all_chunks()
            self.state = "WAITING_FOR_ACK"
            return True
        elif self.state == "WAITING_FOR_ACK":
            if response == FileSharingProtocol.SUCCESS_SIGNAL:
                self.state = "DONE"
                return "COMPLETED"
            elif response.startswith(FileSharingProtocol.NACK_PREFIX):
                try:
                    indices_str = response[len(FileSharingProtocol.NACK_PREFIX):].decode()
                    indices = [int(i) for i in indices_str.split(",") if i.strip()]
                    self.resend_chunks(indices)
                    return True
                except:
                    return False
        return False

    def send_all_chunks(self):
        for i in range(self.num_chunks):
            self.send_chunk(i)

    def send_chunk(self, index):
        header = index.to_bytes(2, byteorder='big')
        payload = header + self.chunks[index]
        self.gw.send(payload)

    def resend_chunks(self, indices):
        for i in indices:
            if 0 <= i < self.num_chunks:
                self.send_chunk(i)

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

    def handle_data(self, data):
        if data.startswith(FileSharingProtocol.HANDSHAKE_PREFIX):
            try:
                info = data[len(FileSharingProtocol.HANDSHAKE_PREFIX):].decode().split("|")
                self.filename = info[0]
                self.num_chunks = int(info[1])
                self.expected_hash = info[2]
                self.received_chunks = {}
                self.state = "RECEIVING"
                self.last_activity = time.time()
                self.gw.send(FileSharingProtocol.READY_SIGNAL)
                return "HANDSHAKE_RECEIVED"
            except:
                return "ERROR"

        if self.state == "RECEIVING":
            if len(data) >= 2:
                try:
                    index = int.from_bytes(data[:2], byteorder='big')
                    chunk_data = data[2:]
                    if 0 <= index < self.num_chunks:
                        self.received_chunks[index] = chunk_data
                        self.last_activity = time.time()

                        if len(self.received_chunks) == self.num_chunks:
                            return self.check_completion()
                        return "CHUNK_RECEIVED"
                except:
                    pass
            return None

        return None

    def check_timeout(self):
        if self.state == "RECEIVING" and self.num_chunks > 0:
            if time.time() - self.last_activity > 15: # 15s idle
                missing = [i for i in range(self.num_chunks) if i not in self.received_chunks]
                if missing:
                    self.request_missing()
                    self.last_activity = time.time() # Reset to avoid spamming
                    return "SENT_NACK"
        return None

    def check_completion(self):
        all_data = b""
        missing = []
        for i in range(self.num_chunks):
            if i in self.received_chunks:
                all_data += self.received_chunks[i]
            else:
                missing.append(i)

        if not missing:
            actual_hash = FileSharingProtocol.get_hash(all_data)
            if actual_hash == self.expected_hash:
                # Sanitize filename to prevent path traversal
                safe_filename = os.path.basename(self.filename)
                filepath = os.path.join(self.save_dir, safe_filename)
                with open(filepath, "wb") as f:
                    f.write(all_data)
                self.gw.send(FileSharingProtocol.SUCCESS_SIGNAL)
                self.state = "DONE"
                return "SUCCESS"
            else:
                # Hash mismatch, something is wrong.
                # In a real protocol we might ask for everything again,
                # but let's just report error for now or maybe it's missing chunks we don't know about.
                return "HASH_MISMATCH"
        else:
            return "MISSING_CHUNKS"

    def request_missing(self):
        missing = [str(i) for i in range(self.num_chunks) if i not in self.received_chunks]
        if missing:
            nack = FileSharingProtocol.NACK_PREFIX + ",".join(missing).encode()
            self.gw.send(nack)

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
