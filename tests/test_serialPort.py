from unittest import TestCase
from unittest.mock import Mock
from serialtcp.serial_port import SerialPort
import serial
from serial.tools import list_ports
import time


class TestSerialPort(TestCase):
    def test_print(self):
        l = (list_ports.comports())
        p_names = [x.device for x in l]
        print(p_names)
        for p in l:
            print(str(p))

    def test_wait_for_com3(self):
        while True:
            l = (list_ports.comports())
            p_names = [x.device for x in l]
            if ('COM3' in p_names):
                print('found')
                break

    def test_print_grep(self):
        l = (list_ports.grep("COM3"))
        for p in l:
            print(str(p))

    def test_send(self):

        on_recv = Mock()
        port = SerialPort(port="COM3", on_received=on_recv, baudrate=921600)
        port.open()

        self.assertTrue(port.is_connected)
        port.send('test'.encode())

        time.sleep(0.5)
        self.assertTrue(port.receive_therad.isAlive())
        on_recv.assert_called_once_with('test'.encode())

        port.close()

    def test_hdisconnect(self):

        on_recv = Mock()
        port = SerialPort(port="COM3", on_received=on_recv, baudrate=921600)
        port.open()

        self.assertTrue(port.is_connected)
        port.send('test'.encode())

        time.sleep(1)
        print('disconnect it')
        time.sleep(9)
        self.assertFalse(port.is_connected)
        self.assertFalse(port.receive_therad.isAlive())

        port.close()

    def test_reconnect(self):
        on_recv = Mock()
        port = SerialPort(port="COM3", on_received=on_recv, baudrate=921600)
        port.open()

        self.assertTrue(port.is_connected)
        port.send('test'.encode())

        time.sleep(1)
        on_recv.assert_called_with('test'.encode())
        print('disconnect it')
        while port.is_connected:
            time.sleep(1)
        self.assertFalse(port.is_connected)
        self.assertFalse(port.receive_therad.isAlive())
        print('now connect')
        while not port.is_connected:
            time.sleep(1)
        self.assertTrue(port.is_connected)
        self.assertTrue(port.receive_therad.isAlive())
        port.send('test2'.encode())
        time.sleep(0.5)
        on_recv.assert_called_with('test2'.encode())

        port.close()
