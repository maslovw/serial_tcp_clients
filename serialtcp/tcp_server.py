import sys
import socket
import serial
import serial.threaded
import time
import threading

import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('Serial')

class SerialToNet(serial.threaded.Protocol):
    """serial->socket
        Receive from the serial port and
        send it to all the tcp clients
    """

    def __init__(self, serial, char_delay=0, wait_echo=0):
        self.socket = []
        self.lastbyte = 0
        self.ser = serial
        self.to_send = None
        self.char_delay = char_delay
        self.wait_echo = wait_echo

    def __call__(self):
        return self

    def send_serial(self, data):
        try:
            if self.char_delay or self.wait_echo:
                for b in data:
                    self.ser.write( bytes([b]))  # get a bunch of bytes and send them
                    if self.char_delay:
                        time.sleep(self.char_delay)
                    if self.wait_echo:
                        if b:
                            t = time.time()
                            while (time.time() - t) < self.wait_echo:
                                if self.lastbyte == b:
                                    self.lastbyte = 0
                                    break
            else:
                self.ser.write(data)
        except Exception as e:
            logger.warning(e)

    def data_received(self, data):
        self.lastbyte = data[-1]
        if len(data)>1:
            logger.debug('Data from {}: {}'.format(self.ser.port, data))
        try:
            for sock in self.socket:
                sock.sendall(data)
        except Exception as e:
            logger.warning(e)


class SerialServer():
    def __init__(self, **kwargs):
        self.port = kwargs['tcp_port']
        self.ser_to_net = None
        self.ser = None
        self.conf = kwargs
        self.stop = False
        char_delay = self.conf.get('char_delay', 0)
        wait_echo = self.conf.get('wait_echo', 0)
        self.serial_worker = None
        self.ser_to_net = SerialToNet(self.ser, char_delay, wait_echo)

    def _connect_serial(self):
        try:
            if self.ser is None:
                self.ser = serial.serial_for_url(self.conf['device'], do_not_open=True)
                self.ser.baudrate = self.conf['baudrate']
                self.ser.parity = self.conf['parity']
                if not self._open_serial():
                    return False

                self.ser_to_net.ser = self.ser
                self.serial_worker = serial.threaded.ReaderThread(self.ser, self.ser_to_net)
                self.serial_worker.start()
            elif not self.ser.is_open:
                return self._open_serial()
            return True
        except Exception as e:
            logger.error("Can not connect to serial: {}".format(e))
            return False

    def _open_serial(self):
        try:
            self.ser.open()
            logger.debug("Device is {} open".format('' if self.ser.is_open else 'not'))
        except Exception as e:
            logger.error("Can not open serial port {}: {}".format(self.conf['device'], e))
            return False
        return True

    def _close_serial(self):
        try:
            if self.serial_worker and self.ser and self.ser.is_open:
                self.serial_worker.close()
                self.ser = None
        except Exception as e:
            logger.warning(e)

    def _make_thread(self, socket, addr):
        logger.info('Connected by {}\n'.format(addr))
        t = threading.Thread(target=SerialServer.worker, args=(self, socket, addr))
        t.start()

    def server_worker(self):
        self.srv.settimeout(1)
        while True:
            try:
                client_socket, addr=self.srv.accept()
            except:
                if self.stop:
                    return
                continue
            if self.stop:
                return
            self._make_thread(client_socket, addr)

    def run(self):
        self.srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.srv.bind(('', self.port))
        self.srv.listen(1)
        t = threading.Thread(target=SerialServer.server_worker, args=(self, ))
        t.start()
        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                self.stop=True
                exit(0)

    def worker(self, client_socket, addr):
        intentional_exit = False
        # More quickly detect bad clients who quit without closing the
        # connection: After 1 second of idle, start sending TCP keep-alive
        # packets every 1 second. If 3 consecutive keep-alive packets
        # fail, assume the client is gone and close the connection.
        try:
            client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 1)
            client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 1)
            client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
            client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except AttributeError:
            pass  # XXX not available on windows
        client_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        client_socket.settimeout(2)
        self.ser_to_net.socket.append(client_socket)
        try:
            client_socket.sendall('Connection established: {}\r\n'.format(addr).encode('utf-8'))
            if self.ser is None:
                conn_ret = self._connect_serial()
            else:
                conn_ret = self.ser.is_open
            if conn_ret:
                client_socket.sendall('Device: {}\r\n'.format(self.ser.port).encode('utf-8'))
                client_socket.sendall('Baudrate: {}\r\n\0'.format(self.ser.baudrate).encode('utf-8'))
                # enter network <-> serial loop
                while True:
                    try:
                        data = client_socket.recv(1024)
                        if not data:
                            break
                        logger.debug('Data from {}: {}'.format(addr,data))
                        self.ser_to_net.send_serial(data)
                    except socket.timeout:
                        if not self.stop:
                            continue
                    except socket.error as msg:
                        logger.error('{}: {}\n'.format(addr, msg))
                        # probably got disconnected
                    if self.stop:
                        break
            else:
                client_socket.sendall('Device: {} is not accessible\r\n\0'.format(self.ser.port).encode('utf-8'))
        except KeyboardInterrupt:
            raise
        except socket.error as msg:
            logger.error('{}: {}\n'.format(addr, msg))
        finally:
            self.ser_to_net.socket.remove(client_socket)
            logger.info('{} is disconnected\n'.format(addr))
            client_socket.close()
            if len(self.ser_to_net.socket) == 0:
                self._close_serial()


if __name__ == '__main__':
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
    # group.add_argument(
    #     '--xonxoff',
    #     action='store_true',
    #     help='enable software flow control (default off)',
    #     default=False)
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
            exit(0)

    for k,v in vars(args).items():
        logger.debug("{}: {}".format(k, v))

    if args.device and args.tcp_port:
        s = SerialServer(**vars(args))
        s.run()

