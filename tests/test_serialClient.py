from unittest import TestCase
import logging
import socket
from time import sleep
from serialtcp.client import SerialClient
logging.basicConfig(level=logging.DEBUG)


class TestSerialClient(TestCase):
    def test_start_stop(self):
        sock = socket.socket()
        client = SerialClient(sock, ('localhost', 1234))
        client.socket.settimeout(0.01)
        client.start()
        sleep(0.01)
        self.assertIsNotNone(client.thread)
        client.stop()
        sleep(1)
        self.assertFalse(client.thread.isAlive())
        self.assertTrue(client.socket._closed)


    def test_append_client(self):
        sock = socket.socket()
        client1 = SerialClient(sock, ('localhost', 1234))
        client1_1 = SerialClient(sock, ('localhost', 1234))
        client2 = SerialClient(sock, ('localhost', 1235))

        self.assertEqual(client1, client1_1)
        self.assertNotEqual(client1, client2)
        clients = {client1, client2}
        clients.remove(client1)
        self.assertEqual(len(clients), 1)
        clients.remove(client2)
        self.assertEqual(len(clients), 0)



