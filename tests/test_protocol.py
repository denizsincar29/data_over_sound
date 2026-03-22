"""
Unit tests for the DataWave protocol and file transfer logic.
"""

import os
import time
import pytest
from typing import List, Tuple
from datawave.core.protocol import Packet, OpCode
from datawave.services.file_transfer import FileSender, FileReceiver, FileTransferProtocol
from tests.simulator import NetworkSimulator

def test_packet_encoding_decoding():
    """Test packet encoding and decoding."""
    payload = b"Hello, World!"
    packet = Packet(OpCode.REMOTE_COMMAND, payload)
    encoded = packet.encode()

    decoded = Packet.decode(encoded)
    assert decoded is not None
    assert decoded.opcode == OpCode.REMOTE_COMMAND
    assert decoded.payload == payload

def test_packet_invalid_preamble():
    """Test decoding with an invalid preamble."""
    invalid_data = b"\x00\x01\x02\x04Hello"
    assert Packet.decode(invalid_data) is None

def test_file_handshake_logic():
    """Test the handshake logic between sender and receiver."""
    # Create a dummy file
    with open("testfile.txt", "wb") as f:
        f.write(b"Hello, world!")

    sender = FileSender("testfile.txt")
    receiver = FileReceiver(save_dir="test_files")

    # 1. Handshake
    handshake = sender.get_handshake_packet()
    status, details = receiver.handle_packet(handshake)

    assert status == "SEND_READY"
    assert receiver.filename == "testfile.txt"
    assert receiver.num_chunks == 1

    # Clean up
    os.remove("testfile.txt")

@pytest.mark.skipif(os.environ.get("GGWAVE_USE_CYTHON") is None and "ggwave" not in os.environ, reason="ggwave environment check")
def test_simulated_transfer():
    """Simulated end-to-end file transfer using the NetworkSimulator."""
    # Create dummy data (2 chunks)
    data = os.urandom(FileTransferProtocol.CHUNK_SIZE + 10)
    with open("sim_test.bin", "wb") as f:
        f.write(data)

    # Track actions on both ends
    node_a_received: List[bytes] = []
    node_b_received: List[bytes] = []

    def node_a_cb(d): node_a_received.append(d)
    def node_b_cb(d): node_b_received.append(d)

    sim = NetworkSimulator(node_a_cb, node_b_cb)
    sender = FileSender("sim_test.bin")
    receiver = FileReceiver(save_dir="sim_files")

    # 1. Handshake (A to B)
    sim.inst1.send(sender.get_handshake_packet().encode())
    time.sleep(1) # Allow for "transmission"

    assert len(node_b_received) == 1
    packet_b = Packet.decode(node_b_received[0])
    status, _ = receiver.handle_packet(packet_b)
    assert status == "SEND_READY"

    # 2. Ready (B to A)
    sender.state = "WAITING_FOR_READY"
    sim.inst2.send(Packet(OpCode.FILE_READY).encode())
    time.sleep(1)

    assert len(node_a_received) == 1
    packet_a = Packet.decode(node_a_received[0])
    action, _ = sender.handle_response(packet_a)
    assert action == "START_SENDING"

    # 3. Data (A to B)
    for i in range(sender.num_chunks):
        sim.inst1.send(sender.get_chunk_packet(i).encode())
        time.sleep(1)
    sim.inst1.send(sender.get_eof_packet().encode())
    time.sleep(1)

    # Process all data chunks on Node B
    for i, raw in enumerate(node_b_received):
        p = Packet.decode(raw)
        if p:
            status, details = receiver.handle_packet(p)
            if status == "SEND_SUCCESS":
                break

    assert receiver.state == "DONE"
    assert os.path.exists("sim_files/sim_test.bin")

    # Cleanup
    os.remove("sim_test.bin")
    if os.path.exists("sim_files/sim_test.bin"):
        os.remove("sim_files/sim_test.bin")
    if os.path.exists("sim_files"):
        os.rmdir("sim_files")
