import unittest
from file_sharing import FileSender, FileReceiver, FileSharingProtocol
import os

class MockGW:
    def __init__(self):
        self.sent_data = []
        self.protocol = 2

    def send(self, data):
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
        sender.send_handshake()
        handshake = self.gw_sender.sent_data.pop(0)
        res = receiver.handle_data(handshake)
        self.assertEqual(res, "HANDSHAKE_RECEIVED")
        self.assertEqual(receiver.state, "RECEIVING")

        # 2. Ready Signal
        ready = self.gw_receiver.sent_data.pop(0)
        self.assertEqual(ready, FileSharingProtocol.READY_SIGNAL)
        res = sender.handle_response(ready)
        self.assertTrue(res)
        self.assertEqual(sender.state, "WAITING_FOR_ACK")

        # 3. Chunks
        chunks_sent = self.gw_sender.sent_data[:]
        self.gw_sender.sent_data = []
        for chunk in chunks_sent:
            res = receiver.handle_data(chunk)
            # res will be CHUNK_RECEIVED or SUCCESS

        self.assertEqual(receiver.state, "DONE")

        # 4. Success Signal
        success = self.gw_receiver.sent_data.pop(0)
        self.assertEqual(success, FileSharingProtocol.SUCCESS_SIGNAL)
        res = sender.handle_response(success)
        self.assertEqual(res, "COMPLETED")
        self.assertEqual(sender.state, "DONE")

        # Verify file content
        with open("files/test_file.txt", "rb") as f:
            content = f.read()
        self.assertEqual(content, b"Hello World! This is a test file for sharing over sound.")

    def test_retransmission(self):
        # Create a larger file to have multiple chunks
        with open(self.test_file, "wb") as f:
            f.write(b"A" * 100) # Should be 2 chunks (64 + 36)

        sender = FileSender(self.gw_sender, self.test_file)
        receiver = FileReceiver(self.gw_receiver)

        # Handshake and Ready
        sender.send_handshake()
        receiver.handle_data(self.gw_sender.sent_data.pop(0))
        sender.handle_response(self.gw_receiver.sent_data.pop(0))

        # Send only first chunk
        chunk0 = self.gw_sender.sent_data.pop(0)
        chunk1 = self.gw_sender.sent_data.pop(0)

        receiver.handle_data(chunk0)
        self.assertEqual(len(receiver.received_chunks), 1)
        self.assertEqual(receiver.state, "RECEIVING")

        # Manually trigger NACK for chunk 1
        receiver.request_missing()
        nack = self.gw_receiver.sent_data.pop(0)
        self.assertTrue(nack.startswith(FileSharingProtocol.NACK_PREFIX))

        # Sender handles NACK
        res = sender.handle_response(nack)
        self.assertTrue(res)

        # Receiver gets retransmitted chunk
        re_chunk1 = self.gw_sender.sent_data.pop(0)
        self.assertEqual(re_chunk1, chunk1)
        res = receiver.handle_data(re_chunk1)
        self.assertEqual(res, "SUCCESS")

if __name__ == "__main__":
    unittest.main()
