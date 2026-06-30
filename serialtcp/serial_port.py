import serial
from serial.tools import list_ports
import time
import logging
import threading

class SerialPort():
    def __init__(self, port, on_received=None,
                 on_connect=lambda:None,
                 on_disconnect=lambda:None,
                 keep_active=True, **kwargs):
        self.serial = serial.Serial()
        self.serial.port = port
        self.serial.baudrate = kwargs.get('baudrate', 9600)
        self.serial.parity = kwargs.get('parity', serial.PARITY_NONE)
        self.serial.timeout = kwargs.get('timeout', 2)
        self.serial.stopbits = kwargs.get('stopbits', serial.STOPBITS_ONE)
        self.serial.xonxoff = kwargs.get('xonxoff', False)

        self.char_mode = kwargs.get('char_mode', False)
        self.wait_echo = kwargs.get('wait_echo', False)
        self.send_char_delay = kwargs.get('char_delay', None)
        self.logger = logging.getLogger("Serial {}".format(port))
        self.is_connected = False
        self.lock = threading.Lock()
        self.lastbyte = 0
        self._on_received = on_received
        if not on_received:
            self._on_received = lambda x: x
        self.receive_thread = None
        self.keep_active = keep_active
        self.reconnect_thread = None
        self._close_set = False
        # Bumped on every successful open. Each receive thread captures the
        # epoch it was started for; a thread whose epoch is stale (a newer
        # open has superseded it) must not touch the port on exit, otherwise a
        # dying receiver from a just-closed connection can close the freshly
        # reopened port and trigger a spurious reconnect.
        self._open_epoch = 0

        self.on_connect = on_connect
        self.on_disconnect = on_disconnect


    def open(self):
        self._close_set = False
        self.__open()

    def ensure_open(self):
        """Open the port for a new consumer unless it is already open.

        Centralises the first-consumer-opens policy shared by the CLI and the
        GUI service: the guard stops a second consumer (TCP client or local
        terminal) from spawning a duplicate receive thread.
        """
        if not self.is_connected:
            self.open()

    def __open(self, throw=False):
        with self.lock:
            try:
                self.serial.open()
            except serial.SerialException as e:
                if not self.serial.is_open:
                    if  throw:
                        raise
                    self.logger.error("open port failed: {}".format(e))
            self.is_connected = self.serial.is_open
            if self.is_connected:
                self.logger.debug("opened port {} at {} baud".format(self.serial.port, self.serial.baudrate))
                self._open_epoch += 1
                epoch = self._open_epoch
                self.receive_thread = threading.Thread(target=self.__async_receiver, args=(epoch,), daemon=True)
                self.receive_thread.start()
            else:
                if self.keep_active:
                    if not self.reconnect_thread or not self.reconnect_thread.is_alive():
                        self.reconnect_thread = threading.Thread(target=self.__try_to_connect, daemon=True)
                        self.reconnect_thread.start()


    def __close(self):
        was_connected = self.is_connected
        if self.serial.is_open:
            self.logger.debug("closing port {}".format(self.serial.port))
            try:
                self.serial.close()
            except Exception as e:
                self.logger.error("close fail: {}".format(e))
        self.is_connected = False
        if was_connected:
            self.on_disconnect()

    def close(self):
        self._close_set = True
        with self.lock:
            self.__close()
        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=3)
        if self.reconnect_thread and self.reconnect_thread.is_alive():
            self.reconnect_thread.join(timeout=3)
            self.reconnect_thread = None

    def on_received(self, data):
        """
        received data from serial
        """
        self.logger.debug("rx: {} bytes".format(len(data)))
        self.lastbyte = data[-1]
        self._on_received(data)

    def __async_receiver(self, epoch):
        self.logger.debug("receiver started")
        self.on_connect()
        while self.serial.is_open and self.is_connected:
            try:
                data = self.serial.read(self.serial.in_waiting or 1)
                if self.serial.in_waiting > 1:
                    data += self.serial.read((self.serial.in_waiting))
                if len(data):
                    self.on_received(data)
            except Exception as e:
                if not self._close_set:
                    self.logger.error("rx fail: {}".format(e))
                break
        # A newer open has taken over (epoch advanced): leave the port to it.
        if epoch != self._open_epoch:
            self.logger.debug("receiver stopped (superseded)")
            return
        if not self._close_set:
            if self.keep_active:
                with self.lock:
                    self.__close()
                    self.reconnect_thread = threading.Thread(target=self.__try_to_connect, daemon=True)
                    self.reconnect_thread.start()
            else:
                self.close()
        self.logger.debug("receiver stopped")

    def __try_to_connect(self):
        self.logger.debug("try to reconnect")
        while not self.serial.is_open and not self._close_set:
            p_list = list_ports.comports()
            p_names = (x.device for x in p_list)
            try:
                if self.serial.port in p_names and not self.serial.isOpen():
                    self.__open(throw=True)
                else:
                    time.sleep(self.serial.timeout)
            except serial.SerialException:
                time.sleep(self.serial.timeout)
        self.logger.debug("try to reconnect stop {} {}".format(self.serial.is_open, self._close_set))


    def __send_chars(self, data):
        for char in data:
            self.serial.write(bytes([char]))  # get a bunch of bytes and send them
            if self.send_char_delay:
                time.sleep(self.send_char_delay)
            if self.wait_echo:
                if char:
                    t = time.time()
                    while (time.time() - t) < self.wait_echo:
                        if self.lastbyte == char:
                            self.lastbyte = 0
                            break

    def send(self, data):
        self.logger.debug("tx: {} bytes".format(len(data)))
        with self.lock:
            try:
                if self.char_mode or self.send_char_delay or self.wait_echo:
                    self.__send_chars(data)
                else:
                    self.serial.write(data)
            except Exception as e:
                self.logger.warning(e)


