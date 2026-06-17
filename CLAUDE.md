# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TCP server that shares a serial console (COM port) over TCP connections. Multiple TCP clients connect to a single serial device through the server. The serial port opens when the first client connects and closes when the last disconnects, with automatic reconnection if the device is lost.

**Package:** `serial_tcp_clients` (v2.0.1-dev)
**Dependencies:** Python >=3.5, pyserial >=3.3

## Common Commands

```bash
# Install in development mode
pip install -e .

# Run the server
python -m serialtcp -p <TCP_PORT> -d <SERIAL_DEVICE> -b <BAUDRATE>

# List available serial ports
python -m serialtcp --list

# Run all tests
python -m pytest tests/

# Run a single test file
python -m pytest tests/test_serialServer.py

# Run a single test
python -m pytest tests/test_serialServer.py::TestSerialServer::test_start_server
```

## Architecture

```
TCP Clients <--> SerialServer <--> SerialPort <--> Serial Device
```

- `tcp_server.py` - CLI entry point (`parse_args()`) and main service orchestration (`start_service()`). Wires callbacks between SerialServer and SerialPort. Status messages are wrapped in STX/ETX markers (`\x02...\x03\r\n`).
- `server.py` - `SerialServer`: multi-client TCP server with accept thread, broadcasts data to all clients.
- `client.py` - `SerialClient`: per-client TCP connection handler with command history (up-arrow replay), keepalive, and error counting.
- `serial_port.py` - `SerialPort`: serial I/O wrapper with background receive thread and auto-reconnect logic.

**Threading model:** One thread per TCP client, one serial receive thread, one serial reconnect thread, one TCP accept thread. Locks protect the client set in SerialServer and serial port state in SerialPort.

**Entry point:** `serialtcp/__main__.py` calls `tcp_server.parse_args()`.
