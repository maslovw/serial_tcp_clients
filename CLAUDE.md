# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TCP server that shares a serial console (COM port) over TCP connections. Multiple TCP clients connect to a single serial device through the server. The serial port opens when the first client connects and closes when the last disconnects, with automatic reconnection if the device is lost.

**Packages (two, both v2.2.3):**
- `serial-tcp-clients` — CLI + headless backend (`serialtcp/`), depends on `pyserial`.
- `serial-tcp-clients-gui` — Tkinter GUI (`gui/serialtcp_gui/`, its own `pyproject.toml`),
  depends on `serial-tcp-clients` + `PyYAML` (and Tkinter).

**Dependencies:** Python >=3.9, pyserial >=3.3 (GUI also: PyYAML >=5.1, Tkinter)

## Common Commands

```bash
# Install in development mode (CLI only; add `-e gui` for the GUI package too)
pip install -e . -e gui

# Run the server
python -m serialtcp -p <TCP_PORT> -d <SERIAL_DEVICE> -b <BAUDRATE>

# List available serial ports
python -m serialtcp --list

# Run the Tkinter Port Manager GUI (manages many mappings from a YAML config)
python -m serialtcp_gui [config.yaml]

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

### GUI (Port Manager) — `serial-tcp-clients-gui` package

A Tkinter app (in `gui/serialtcp_gui/`, packaged separately from the CLI) that
manages many serial->TCP mappings at once from a YAML config.

- `serialtcp/service.py` - `PortConfig` (one mapping) and `PortService`: a headless wrapper that wires one `SerialServer` + one `SerialPort` together without the CLI's signals/blocking loop. Counts tx/rx bytes, tracks status/clients/uptime/reconnect attempts, and reports console lines through an `on_event(service, event)` callback. **Lives in the base `serialtcp` package** (no Tkinter/PyYAML) — the reusable backend seam the GUI builds on.
- `gui/serialtcp_gui/` - `app.py` (window, master-detail layout, `queue`+`after` event loop), `port_card.py` (master list card), `detail.py` (running/reconnecting/stopped/empty states + console), `dialog.py` (add/edit), `about.py`, `widgets.py`/`theme.py`/`util.py`/`config.py`/`ansi.py` (themed widgets, design tokens, helpers, YAML load/save, ANSI parsing).

**GUI threading:** backend I/O threads only enqueue events; all Tk widget mutation happens on the main loop (`App._tick` drains the queue via `after`). Design reference lives in `PROMPT/design_handoff_serial_tcp_port_manager/`.

**Packaging:** two distributions from one repo — base `pyproject.toml` (root) builds `serial-tcp-clients` from `serialtcp/`; `gui/pyproject.toml` builds `serial-tcp-clients-gui` from `gui/serialtcp_gui/`. Root `conftest.py` puts `gui/` on `sys.path` so the suite imports `serialtcp_gui` without an install. `serialtcp_gui` keeps its own `__version__` (kept in lockstep with `serialtcp.__version__`).
