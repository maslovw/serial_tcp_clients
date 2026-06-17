# serial-tcp-server

TCP server for sharing a serial console across multiple TCP clients.

```
clientA <-->\
             | <-----> TcpServer <---> serial port
clientB <-->/
```

The serial port opens when the first client connects and closes when
the last client disconnects. If the serial device is lost, all TCP
clients are kept connected while the server attempts to reconnect.

Works on Windows and Linux (including Raspberry Pi).

## Requirements

- Python >= 3.9
- pyserial >= 3.3

## Install

```bash
pip install serial-tcp-clients
```

Or from source:

```bash
git clone https://github.com/maslovw/serial_tcp_clients.git
cd serial_tcp_clients
pip install .
```

## Usage

```bash
serial-tcp-server -p PORT -d DEVICE -b BAUDRATE
```

Or via module:

```bash
python -m serialtcp -p PORT -d DEVICE -b BAUDRATE
```

### Arguments

```
optional arguments:
  -h, --help            show this help message and exit
  --list                print list of serial devices
  -v {debug,info,warn,error,fatal}, --verbose {debug,info,warn,error,fatal}
                        logger level, default: error

TCP connection:
  -p TCP_PORT, --tcp-port TCP_PORT
                        TCP listen port

serial port:
  -d DEVICE, --device DEVICE
                        serial port/device
  -b BAUDRATE, --baudrate BAUDRATE
                        default: 115200
  --parity {N,E,O,S,M}  set parity, one of {N E O S M}, default: N
  --xonxoff             enable software flow control (default off)
  -cd CHAR_DELAY, --char-delay CHAR_DELAY
                        set delay between chars for serial transmission,
                        default: 0.0s
  -we WAIT_ECHO, --wait-echo WAIT_ECHO
                        wait for echo char when transmitting, value represents
                        timeout in seconds, default: 0
```

### Example

```bash
serial-tcp-server -p 5001 -d COM1 -b 921600 -v info -we 1
```

Use `-v debug` to send connection status messages (device, baudrate,
connect/disconnect events) to TCP clients.

## GUI (Port Manager)

The package ships an optional **Tkinter desktop app** that manages **many**
serial -> TCP mappings at once from a single YAML config. It uses a
master-detail layout: a list of port cards on the left, and the selected port's
console, settings, throughput and live log on the right.

```
+-------------------------------------------------------------+
| Port Manager            3 mappings  [Start all] [Stop all] +|
+----------------------+--------------------------------------+
| COM103   -> :5000  > | COM103  -> 0.0.0.0:5000      [Stop]  |
|   Running            | Running . uptime 00:12:44            |
|   OUT 2 B/s  IN 30   | [CLIENTS 1][TX 142KB][RX 1.2MB][BAUD]|
+----------------------+ SERIAL  8N1  parity N  xon/xoff off  |
| COM4     -> :5001  > | +----------------------------------+ |
|   Stopped            | | CONSOLE - COM103          * live | |
+----------------------+ | [12:05] client connected         | |
| + Add serial -> TCP  | | [12:05] U-Boot 2021.07 ...       | |
+----------------------+ +----------------------------------+ |
+-------------------------------------------------------------+
```

For each mapping you can Start/Stop the TCP listener, watch live OUT/IN
throughput and the connected-client count, read a colour-coded console, send
data to the serial device from a console input line, and Add/Edit/Remove
mappings. The serial port opens when the first TCP client connects and closes
when the last disconnects; if the device drops, the clients stay connected while
the GUI shows a "reconnecting" banner and retries.

### Requirements

- Python >= 3.9
- pyserial >= 3.3 and PyYAML >= 5.1 (both pulled in by the `[gui]` extra)
- Tkinter — bundled with the standard Python installers on **Windows** and
  **macOS**. On Linux, install it from your package manager
  (Debian/Ubuntu: `sudo apt install python3-tk`).

### Build / install

**From PyPI:**

```bash
pip install "serial-tcp-clients[gui]"
```

**From source (recommended for development) — Windows:**

```bat
git clone https://github.com/maslovw/serial_tcp_clients.git
cd serial_tcp_clients
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[gui]"
```

**From source — Linux / macOS:**

```bash
git clone https://github.com/maslovw/serial_tcp_clients.git
cd serial_tcp_clients
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[gui]"
```

**Standalone Windows executable (no Python needed on the target machine):**

```bat
deploy\build-gui.bat
```

This uses PyInstaller to produce a single windowed binary `serial-tcp-gui.exe`
in the repository root. It builds in a throwaway virtualenv, so it does not
touch your working `.venv`. Pass an explicit interpreter if `python` is not on
your PATH: `deploy\build-gui.bat C:\Python310\python.exe`.

### Start / run

With the package installed (console script on PATH):

```bash
serial-tcp-gui                 # loads ./serialtcp_ports.yaml if present
serial-tcp-gui ports.yaml      # load a specific config
```

As a module (works without the console script on PATH):

```bash
python -m serialtcp.gui ports.yaml
```

From a source venv on Windows, or the standalone build:

```bat
.venv\Scripts\serial-tcp-gui.exe ports.yaml
serial-tcp-gui.exe ports.yaml
```

If no config path is given, the app uses `./serialtcp_ports.yaml`. Any mapping
you Add/Edit/Remove in the GUI is **saved back** to that file.

### Configuration file

A YAML file with a `ports:` list; each entry binds one serial device to one TCP
listen port. Only `device` and `tcp_port` are required — everything else has
sensible defaults.

```yaml
ports:
  - name: COM103          # optional label (defaults to the device name)
    device: COM103        # COM103 on Windows, /dev/ttyUSB0 on Linux
    tcp_port: 5000        # TCP port that clients connect to
    baudrate: 921600
    parity: N             # one of N E O S M
    xonxoff: false        # software flow control
    char_mode: false      # send characters one at a time
    char_delay: 0.0       # seconds between characters
    wait_echo: 0.0        # seconds to wait for echo per character
    allow_remote: false   # false = listen on 127.0.0.1 only; true = 0.0.0.0
    autostart: true       # start listening as soon as the GUI opens
```

By default a mapping listens on **`127.0.0.1`** (localhost only), so the serial
console is not exposed on the network. Set `allow_remote: true` (or tick
**Allow remote connections** in the Add/Edit dialog) to bind `0.0.0.0` and accept
connections from other machines.

A ready-to-edit example lives in [`ports.example.yaml`](ports.example.yaml).

### Using it

- **Start / Stop** a port from its card or the detail panel; **Start all** and
  **Stop all** are in the top bar.
- **＋ Add serial → TCP port** (top bar or the dashed list footer) opens a dialog
  to choose the serial device, baudrate, parity, flow/char options and the TCP
  listen port. **Edit** changes a mapping; **Remove** deletes a stopped one.
- Connect any TCP client to the listen port to talk to the device, e.g.:

  ```bash
  telnet localhost 5000
  ```

  or PuTTY (connection type *Raw* or *Telnet*, host `localhost`, port `5000`),
  or `nc localhost 5000`. Several clients can share one serial device at once.
