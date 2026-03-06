from unittest import TestCase
from unittest.mock import Mock
import unittest
from serialtcp.server import SerialServer
import socket
import threading
import time
import logging
logging.basicConfig(level=logging.DEBUG)

class TestSerialServer(TestCase):
    def test_run(self):
        server = SerialServer(1234)
        server.run()
        server.ready.wait(2)

        self.assertTrue(server.thread_accept.is_alive())
        server.stop()
        self.assertFalse(server.thread_accept.is_alive())

    def test_one_client(self):
        server = SerialServer(1234)
        server.run()
        server.ready.wait(2)

        client = socket.socket()
        client.connect(('localhost', server.port))
        time.sleep(0.5)
        self.assertEqual(1, len(server.clients))

        server.stop()
        client.close()
        self.assertEqual(0, len(server.clients))

    def test_two_clients(self):
        server = SerialServer(1234)
        server.run()
        server.ready.wait(2)

        client1 = socket.socket()
        client1.connect(('localhost', server.port))
        time.sleep(0.5)

        client2 = socket.socket()
        client2.connect(('localhost', server.port))
        time.sleep(0.5)

        self.assertEqual(2, len(server.clients))

        server.stop()
        client1.close()
        client2.close()
        self.assertEqual(0, len(server.clients))

    def test_two_clients_disconnect(self):
        server = SerialServer(1234)
        server.run()
        server.ready.wait(2)

        client1 = socket.socket()
        client2 = socket.socket()

        client1.connect(('localhost', server.port))
        time.sleep(0.5)

        client1.close()
        time.sleep(0.5)

        client2.connect(('localhost', server.port))
        time.sleep(0.5)

        server.stop()
        client2.close()
        self.assertEqual(0, len(server.clients))

    def test_one_client_send(self):
        server = SerialServer(1234)
        server.run()
        server.ready.wait(2)

        client = socket.socket()
        client.connect(('localhost', server.port))
        time.sleep(0.5)
        onRecv = Mock()
        list(server.clients)[0].set_on_received(onRecv)
        client.sendall("test".encode())
        time.sleep(0.5)
        onRecv.assert_called_once_with("test".encode())

        server.stop()
        client.close()
        self.assertEqual(0, len(server.clients))

    @unittest.skip("manual test")
    def test__open_server(self):
        server = SerialServer(1234)
        server.run()
        server.ready.wait(2)
        time.sleep(60)

        server.stop()
        self.assertEqual(0, len(server.clients))
