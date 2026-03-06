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
