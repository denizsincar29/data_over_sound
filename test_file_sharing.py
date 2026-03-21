import unittest
from file_sharing import FileSender, FileReceiver, FileSharingProtocol
import os

class MockGW:
    def __init__(self):
        self.sent_data = []
        self.protocol = 2

    def send(self, data, protocol=None):
        self.sent_data.append(data)

    def switchinstance(self, pl):
        pass

class TestFileSharing(unittest.TestCase):
    def setUp(self):
        self.test_file = "test_file.txt"
        with open(self.test_file, "wb") as f:
            f.write(b"Hello World! This is a test file for sharing over sound.")
        self.gw_sender = MockGW()
        self.gw_receiver = MockGW()

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        if os.path.exists("files/test_file.txt"):
            os.remove("files/test_file.txt")

    def test_protocol_flow(self):
        sender = FileSender(self.gw_sender, self.test_file)
        receiver = FileReceiver(self.gw_receiver)

        # 1. Handshake
        handshake = sender.get_handshake_data()
        sender.state = "WAITING_FOR_READY"
        status, details = receiver.handle_data(handshake)
        self.assertEqual(status, "SEND_READY")
        self.assertEqual(details, FileSharingProtocol.READY_SIGNAL)
        self.assertEqual(receiver.state, "RECEIVING")

        # 2. Ready Signal
        ready = FileSharingProtocol.CONTROL_BYTE + details
        action, details = sender.handle_response(ready)
        self.assertEqual(action, "START_SENDING")
        self.assertEqual(sender.state, "SENDING_CHUNKS")

        # 3. Chunks
        for i in range(sender.num_chunks):
            chunk = sender.get_chunk_data(i)
            status, details = receiver.handle_data(chunk)
            if i == sender.num_chunks - 1:
                self.assertEqual(status, "SEND_SUCCESS")
            else:
                self.assertEqual(status, "CHUNK_RECEIVED")

        # 4. EOF (ignored because already DONE)
        eof = sender.get_eof_data()
        status, details = receiver.handle_data(eof)
        self.assertIsNone(status)
        self.assertEqual(receiver.state, "DONE")

        # 5. Success Signal
        success = FileSharingProtocol.CONTROL_BYTE + FileSharingProtocol.SUCCESS_SIGNAL
        action, details = sender.handle_response(success)
        self.assertEqual(action, "COMPLETED")
        self.assertEqual(sender.state, "DONE")

        # Verify file content
        with open("files/test_file.txt", "rb") as f:
            content = f.read()
        self.assertEqual(content, b"Hello World! This is a test file for sharing over sound.")

    def test_retransmission(self):
        # Create a file that fits in exactly 2 chunks
        chunk_size = FileSharingProtocol.CHUNK_SIZE
        with open(self.test_file, "wb") as f:
            f.write(b"A" * (chunk_size + 10))

        sender = FileSender(self.gw_sender, self.test_file)
        receiver = FileReceiver(self.gw_receiver)

        # Handshake and Ready
        handshake = sender.get_handshake_data()
        sender.state = "WAITING_FOR_READY"
        status, ready_data = receiver.handle_data(handshake)
        sender.handle_response(FileSharingProtocol.CONTROL_BYTE + ready_data)

        # Receiver gets only chunk 0
        chunk0 = sender.get_chunk_data(0)
        receiver.handle_data(chunk0)
        self.assertEqual(len(receiver.received_chunks), 1)
        self.assertEqual(receiver.state, "RECEIVING")

        # Receiver gets EOF, triggering NACK
        eof = sender.get_eof_data()
        status, details = receiver.handle_data(eof)
        self.assertEqual(status, "SEND_NACK")
        self.assertEqual(details, [1])

        # Sender handles NACK
        nack = FileSharingProtocol.CONTROL_BYTE + FileSharingProtocol.NACK_PREFIX + b"1"
        action, details = sender.handle_response(nack)
        self.assertEqual(action, "RESEND_CHUNKS")
        self.assertEqual(details, [1])

        # Receiver gets retransmitted chunk 1
        re_chunk1 = sender.get_chunk_data(1)
        status, details = receiver.handle_data(re_chunk1)
        self.assertEqual(status, "SEND_SUCCESS")

    def test_timeout_retry_ready(self):
        sender = FileSender(self.gw_sender, self.test_file)
        receiver = FileReceiver(self.gw_receiver)

        # Handshake
        receiver.handle_data(sender.get_handshake_data())
        self.assertEqual(receiver.ready_sent_count, 1)

        # Mock timeout
        receiver.last_activity -= 20
        status, details = receiver.check_timeout()
        self.assertEqual(status, "SEND_READY")
        self.assertEqual(receiver.ready_sent_count, 2)

        # Mock timeout again
        receiver.last_activity -= 20
        status, details = receiver.check_timeout()
        self.assertEqual(status, "SEND_READY")
        self.assertEqual(receiver.ready_sent_count, 3)

        # Mock timeout again -> Abort
        receiver.last_activity -= 20
        status, details = receiver.check_timeout()
        self.assertEqual(status, "ABORT")
        self.assertEqual(receiver.state, "IDLE")

    def test_protocol_switch_logic(self):
        # This test checks the logic for protocol switching before handshake
        # Since the switch is in cli.py/main.py, we can only verify the state expectations here
        self.assertEqual(FileSharingProtocol.FILE_PROTOCOL, 2)

if __name__ == "__main__":
    unittest.main()
