# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TCP server that shares a serial console (COM port) over TCP connections. Multiple TCP clients connect to a single serial device through the server. The serial port opens when the first client connects and closes when the last disconnects, with automatic reconnection if the device is lost.

**Packages (two, both v2.6.0):**
- `serial-tcp-clients` — CLI + headless backend (`serialtcp/`), depends on `pyserial`.
- `serial-tcp-clients-gui` — Tkinter GUI (`gui/serialtcp_gui/`, its own `pyproject.toml`),
  depends on `serial-tcp-clients` + `PyYAML` (and Tkinter). Optional `[api]` extra
  (fastapi + uvicorn) enables the REST control interface.

**Dependencies:** Python >=3.9, pyserial >=3.3 (GUI also: PyYAML >=5.1, Tkinter;
GUI `[api]` extra: fastapi >=0.100, uvicorn >=0.20)

## Common Commands

```bash
# Install in development mode (CLI only; add `-e gui` for the GUI package too,
# or `-e "gui[api]"` to also pull in the REST API dependencies)
pip install -e . -e gui

# Run the server
python -m serialtcp -p <TCP_PORT> -d <SERIAL_DEVICE> -b <BAUDRATE>

# List available serial ports
python -m serialtcp --list

# Run the Tkinter Port Manager GUI (manages many mappings from a YAML config)
python -m serialtcp_gui [config.yaml]

# Control a running GUI through its REST API (console script: serial-tcp-ctl)
python -m serialtcp_gui.cli health
python -m serialtcp_gui.cli ports

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
- `gui/serialtcp_gui/` - `app.py` (window, master-detail layout, `queue`+`after` event loop), `port_card.py` (master list card), `detail.py` (running/reconnecting/stopped/empty states + console), `dialog.py` (add/edit), `about.py`, `api.py` (REST control interface), `widgets.py`/`theme.py`/`util.py`/`config.py`/`ansi.py` (themed widgets, design tokens, helpers, YAML load/save, ANSI parsing).

**GUI threading:** backend I/O threads only enqueue events; all Tk widget mutation happens on the main loop (`App._tick` drains the queue via `after`). Design reference lives in `PROMPT/design_handoff_serial_tcp_port_manager/`.

**REST API (optional):** `api.py` serves FastAPI on a uvicorn daemon thread (config block `api:`, default `127.0.0.1:410`). `GuiController` answers reads straight from `PortService` and routes every mutation through `App.call_on_main`, a second queue drained by `App._tick`, so widget mutation stays on the main loop. The endpoints drive `App`'s public control surface (`add_port_config`, `update_port_config`, `remove_port_config`, `start_service`, `stop_service`) — the same calls the GUI handlers use. Tests: `tests/test_gui_api.py` (TestClient + the Tk-free `FakeApp` in `tests/conftest.py`).

**API CLI client:** `cli.py` (console script `serial-tcp-ctl`) is the command-line counterpart — one subcommand per endpoint, stdlib only (urllib), so it needs neither Tkinter nor the `[api]` extra. Target URL comes from `--url` (port / host:port / URL), else the config file's `api:` block, else `http://127.0.0.1:410`. Tests: `tests/test_gui_cli.py` run the real `main()` against a real `ApiServer`.

**Packaging:** two distributions from one repo — base `pyproject.toml` (root) builds `serial-tcp-clients` from `serialtcp/`; `gui/pyproject.toml` builds `serial-tcp-clients-gui` from `gui/serialtcp_gui/`. Root `conftest.py` puts `gui/` on `sys.path` so the suite imports `serialtcp_gui` without an install. `serialtcp_gui` keeps its own `__version__` (kept in lockstep with `serialtcp.__version__`).
