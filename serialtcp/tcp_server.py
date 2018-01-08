
from serialtcp.server import SerialServer
from serialtcp.serial_port import SerialPort
import time

import logging

logger = logging.getLogger('Main')


def start_service(**kwargs):
    tcp_port = kwargs['tcp_port']
    device = kwargs.get('device', None)

    stop = []
    def on_tcp_receive(data):
        if 'exit\xff'.encode() in data:
            stop.append(1)
        else:
            serial_port.send(data)

    def on_serial_receive(data):
        server.send_to_all(data)

    def on_tcp_connect(client):
        if not serial_port.is_connected:
            serial_port.open()

        client.send('\x02Device: {}\x03\r\n'.format(device).encode())
        client.send('\x02Baudrate: {}\x03\r\n'.format(serial_port.serial.baudrate).encode())
        if not serial_port.is_connected:
            client.send('\x02Device: {} is not accessible\x03\r\n'.format(serial_port.serial.port).encode())

    def on_tcp_disconnect(client):
        if len(server.get_clients()) == 0:
            serial_port.close()

    def on_serial_connect():
        server.send_to_all('\x02Device: {} is connected\x03\r\n'.format(serial_port.serial.port).encode())

    def on_serial_disconnect():
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

    # serial_port.open()
    server.run()

    while True:
        try:
            time.sleep(1)
        except KeyboardInterrupt:
            print("Keyboard Interrupt")
            break
        if len(stop):
            print("STOP!")
            break

    server.send_to_all('\x02Session is closed\x03\r\n\x04'.encode())
    server.stop()
    serial_port.close()

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

    logger.setLevel(args.verbose.upper())

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
