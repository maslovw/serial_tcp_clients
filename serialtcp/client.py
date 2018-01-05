import socket
import threading
import logging
from collections import deque


class SerialClient():
    MAX_ERROR = 5

    def __init__(self, client_socket: socket.socket,
                 address,
                 on_disconnect=lambda self: None,
                 on_connect=lambda self: None,
                 on_received=lambda data: None):
        self.socket = client_socket
        self.address = address
        self.thread = None
        self._stop = False
        self._buffersize = 1024
        self.logger = logging.getLogger("Client{}".format(address))
        self.err_cnt = 0
        # self._on_received = (lambda x: None) if on_received is None else on_received
        try:
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 1)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 1)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except AttributeError:
            pass  # XXX not available on windows
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.socket.settimeout(2)
        self.history = deque(maxlen=10)

        self._on_received = on_received
        self._on_disconnect = on_disconnect
        self._on_connect = on_connect

    def __eq__(self, other):
        return self.address == other.address

    def __hash__(self):
        return hash(self.address)

    def set_on_received(self, on_received):
        self._on_received = on_received

    def start(self):
        self.logger.debug("start")

        self.err_cnt = 0
        self.thread = threading.Thread(target=SerialClient.run, args=(self, ))
        self.thread.start()

    def on_received(self, data):
        """
        Dummy method
        Data received from TCP
        """
        self.logger.debug("received: {}".format(data))
        if '\x1b[A\r'.encode() in data:
            self.send(self.history.pop())
        else:
            self.history.append(data)
        self._on_received(data)

    def send(self, data):
        """
        Send from serial to the TCP socket
        :param data:
        :return:
        """
        self.logger.debug("send: {}".format(data))
        self.socket.sendall(data)

    def stop(self):
        self._stop = True

    def run(self):
        self.logger.info('connected')
        try:
            self.socket.sendall('Connection established: {}\r\n'.format(self.address).encode())
        except Exception as e:
            self.logger.error('send connection data failed: {}'.format(e))
            self.err_cnt += 1

        self._on_connect(self)

        while not self._stop:
            try:
                data = self.socket.recv(self._buffersize)
                if len(data):
                    self.on_received(data)
                else:
                    self.logger.error("receive null")
                    self.err_cnt += 1
            except socket.timeout:
                continue
            except Exception as e:
                self.logger.error("receive failed: {}".format(e))
                self.err_cnt += 1
            if self.err_cnt > self.MAX_ERROR:
                self.logger.warning("error count > {}".format(self.MAX_ERROR))
                self.stop()
        self.logger.debug("stop")
        self.socket.close()
        self._on_disconnect(self)
        # self.thread = None
