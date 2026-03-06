
from serialtcp.server import SerialServer
from serialtcp.serial_port import SerialPort
import time
import signal
import sys

import logging

logger = logging.getLogger('Main')


def start_service(**kwargs):
    tcp_port = kwargs['tcp_port']
    device = kwargs.get('device', None)
    debug = kwargs.get('verbose', 'error') == 'debug'

    stop = []

    def request_stop(*args):
        stop.append(1)

    signal.signal(signal.SIGTERM, request_stop)
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, request_stop)

    def strip_telnet_commands(data):
        """Remove Telnet IAC sequences (3-byte commands) from data."""
        result = bytearray()
        i = 0
        while i < len(data):
            if data[i] == 0xff and i + 2 < len(data) and data[i + 1] in (0xfb, 0xfc, 0xfd, 0xfe):
                i += 3  # skip IAC WILL/WONT/DO/DONT <option>
            else:
                result.append(data[i])
                i += 1
        return bytes(result)

    def on_tcp_receive(data):
        if 'exit\xff'.encode() in data:
            stop.append(1)
        else:
            if kwargs.get('char_mode', False):
                data = strip_telnet_commands(data)
                if not data:
                    return
            serial_port.send(data)

    def on_serial_receive(data):
        server.send_to_all(data)

    # Telnet negotiation: switch client to character-at-a-time mode
    TELNET_CHAR_MODE = b'\xff\xfb\x01' \
                       b'\xff\xfb\x03'  # IAC WILL ECHO, IAC WILL SUPPRESS-GO-AHEAD

    def on_tcp_connect(client):
        logger.debug("tcp client connected: {}".format(client.address))
        if not serial_port.is_connected:
            logger.debug("opening serial port for first client")
            serial_port.open()

        if kwargs.get('char_mode', False):
            client.send(TELNET_CHAR_MODE)

        if debug:
            client.send('Connection established: {}\r\n'.format(client.address).encode())
            client.send('\x02Device: {}\x03\r\n'.format(device).encode())
            client.send('\x02Baudrate: {}\x03\r\n'.format(serial_port.serial.baudrate).encode())
            if not serial_port.is_connected:
                client.send('\x02Device: {} is not accessible\x03\r\n'.format(serial_port.serial.port).encode())

    def on_tcp_disconnect(client):
        remaining = len(server.get_clients())
        logger.debug("tcp client disconnected: {}, remaining: {}".format(client.address, remaining))
        if remaining == 0:
            logger.debug("last client disconnected, closing serial port")
            serial_port.close()

    def on_serial_connect():
        logger.debug("serial device connected: {}".format(serial_port.serial.port))
        if debug:
            server.send_to_all('\x02Device: {} is connected\x03\r\n'.format(serial_port.serial.port).encode())

    def on_serial_disconnect():
        logger.debug("serial device disconnected: {}".format(serial_port.serial.port))
        if debug:
            server.send_to_all('\x02Device: {} is disconnected\x03\r\n'.format(serial_port.serial.port).encode())

    serial_port = SerialPort(device,
                             on_received=on_serial_receive,
                             on_connect=on_serial_connect,
                             on_disconnect=on_serial_disconnect,
                             keep_active=True,
                             **kwargs)

    server = SerialServer(tcp_port,
                          on_tcp_receive=on_tcp_receive,
                          on_client_connect=on_tcp_connect,
                          on_client_disconnect=on_tcp_disconnect)

    logger.debug("starting service on tcp port {} for device {}".format(tcp_port, device))
    server.run()

    while not stop:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            break

    logger.debug("shutting down service")
    server.send_to_all('\x02Session is closed\x03\r\n\x04'.encode())
    server.stop()
    serial_port.close()
    logger.debug("service stopped")

def parse_args():
    from serial.tools import list_ports
    import argparse

    aparse = argparse.ArgumentParser(description='Serial to TCP splitter')
    aparse.add_argument(
        '--list',
        action='store_true',
        help='print list of serial devices',
        default=False
    )

    aparse.add_argument(
        '-v', '--verbose',
        choices=['debug', 'info', 'warn', 'error', 'fatal'],
        type=lambda c: c.lower(),
        help='logger level, default: error',
        default='error'
    )

    group_tcp = aparse.add_argument_group('TCP connection')

    group_tcp.add_argument(
        '-p', '--tcp-port',
        type=int,
        help='TCP listen port'
    )

    group = aparse.add_argument_group('serial port')

    group.add_argument(
        '-d', '--device',
        help='serial port/device'
    )
    group.add_argument(
        '-b', '--baudrate',
        type=int,
        help='default: 115200',
        default=115200
    )
    group.add_argument(
        "--parity",
        choices=['N', 'E', 'O', 'S', 'M'],
        type=lambda c: c.upper(),
        help="set parity, one of {N E O S M}, default: N",
        default='N')

    # group.add_argument(
    #     '--rtscts',
    #     action='store_true',
    #     help='enable RTS/CTS flow control (default off)',
    #     default=False)
    #
    group.add_argument(
        '--xonxoff',
        action='store_true',
        help='enable software flow control (default off)',
        default=False)
    #
    # group.add_argument(
    #     '--rts',
    #     type=int,
    #     help='set initial RTS line state (possible values: 0, 1)',
    #     default=None)
    #
    # group.add_argument(
    #     '--dtr',
    #     type=int,
    #     help='set initial DTR line state (possible values: 0, 1)',
    #     default=None)

    group.add_argument(
        '-cm', '--char-mode',
        action='store_true',
        help='send characters one at a time to serial (default off)',
        default=False
    )

    group.add_argument(
        '-cd', '--char-delay',
        type=float,
        help='set delay between chars for serial transmission, default: 0.0s',
        default=0
    )

    group.add_argument(
        '-we', '--wait-echo',
        type=float,
        help='wait for echo char when transmitting, value represents timeout in seconds, default: 0',
        default=0
    )

    args = aparse.parse_args()

    log_fmt = '[%(asctime)s:%(msecs)03d]:%(name)s:%(levelname)s:%(message)s'
    log_datefmt = '%d.%m.%y %H:%M:%S'
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(args.verbose.upper())
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(log_fmt, datefmt=log_datefmt))
    root.addHandler(handler)

    if args.list:
        for port in list_ports.comports(True):
            print(port.device)
        return

    for k,v in vars(args).items():
        logger.debug("{}: {}".format(k, v))

    if args.device and args.tcp_port:
        print("Device {args.device} <-> TCP {args.tcp_port}".format(**locals()))
        start_service(**vars(args))
    else:
        if not args.device:
            print("No device specified, see --help")
        if not args.tcp_port:
            print("No tcp port specified, see --help")
        # s = SerialServer(**vars(args))
        # s.run()


if __name__ == '__main__':
    parse_args()
