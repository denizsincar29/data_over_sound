# DataWave

A Python program for transmitting and receiving data over sound waves using only a speaker and a microphone.

## Description

DataWave is a refactored and improved version of the original Data Over Sound program. It allows you to transmit and receive data between two devices using only audio. This is especially useful for air-gapped devices or when no traditional network is available.

DataWave features a robust binary protocol with a 4-byte header (3-byte preamble + 1-byte opcode) to ensure that control signals (like file handshakes and remote commands) are never accidentally triggered by raw text.

## How It Works

The program utilizes the [ggwave](https://github.com/ggerganov/ggwave) library to encode and decode data into sound waves. DataWave adds a protocol layer on top to handle:
- **Text Messaging**: Reliable exchange of UTF-8 text.
- **File Transfer**: Multi-chunk file transfer with handshakes, NACK-based retransmission, and MD5 verification.
- **Remote Control**: Executing commands on a remote device and querying available remote functions.

## Installation

### Prerequisites

**UV Package Manager**: This project uses UV for dependency management.

```bash
# On macOS and Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using pip
pip install uv
```

### Building ggwave

DataWave requires `ggwave` with Cython support on Python 3.11+.

```bash
export GGWAVE_USE_CYTHON=1
uv sync
```

## Usage

### Running the Application

DataWave supports both a GUI (wxPython) and a CLI.

**To run the GUI (default):**
```bash
uv run -m datawave
```

**To run the CLI:**
```bash
uv run -m datawave --cli
```

### CLI Commands

Type commands starting with `/` in the CLI:
- **/help**: Displays a list of commands.
- **/sendfile <path>**: Initiate a file transfer.
- **/query**: Query the remote device for its available commands.
- **/remote <name> [args]**: Execute a command on the remote device.
- **/protocol <num> [payload_len]**: Change the encoding protocol and optional payload length.
- **/open**: Parse and open URLs, emails, or phone numbers from the last received message.
- **/exit**: Exit the program.

## Protocols

DataWave supports the standard ggwave protocols (0-11):
- **0-2**: Dual-tone, Middle frequency (Fastest is 2).
- **3-5**: Dual-tone, Ultrasonic (Fastest is 5).
- **6-8**: Dual-tone, Low frequency with ECC.
- **9-11**: Single-tone with ECC (Requires fixed payload length, default 32).

## Architecture

The project is organized into a clean package structure:
- `datawave.core`: Audio engine, stream management, and protocol packet handling.
- `datawave.services`: File transfer and remote control logic.
- `datawave.ui`: GUI and CLI implementations.
- `datawave.utils`: Settings, parsing, and accessibility utilities.

## Testing

DataWave includes a simulator for testing the protocol without physical audio hardware.

```bash
GGWAVE_USE_CYTHON=1 uv run --extra test pytest
```

## License

This project is licensed under the MIT License.
