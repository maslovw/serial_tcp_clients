# Info
Python script starts TCP Server for sharing serial console

```
clientA <-->\
             | <-----> TcpServer <---> serial port
clientB <-->/
```
Serial port is opened if at least one client is connected. 

If all clients are disconnected, then the serial port is closed.

Works in Windows and Linux (incl. RaspberryPi) 

# Requerements
python3
* pyserial (https://github.com/pyserial/pyserial)

# Install
`git clone https://github.com/maslovw/serial_tcp_clients.git`

`cd serial_tcp_clients`

`python3 setup.py install`

# Usage
`python -m serialtcp.tcp_server -p PORT -d COM -b BAUDRATE`

## Arguments:
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
  -cd CHAR_DELAY, --char-delay CHAR_DELAY
                        set delay between chars for serial transmission,
                        default: 0.0s
  -we WAIT_ECHO, --wait-echo WAIT_ECHO
                        wait for echo char when transmitting, value represents
                        timeout in seconds, default: 0
```

## example
`python -m serialtcp.tcp_server -p 5001 -d COM1 -b 921600 -v info -we 1`
