import socket
from copy import deepcopy
import time
import threading
from serialtcp.client import SerialClient
import logging


class SerialServer():
    def __init__(self, port,
                 on_tcp_receive=lambda data:None,
                 on_client_connect=lambda client:None,
                 on_client_disconnect=lambda client:None ):
        # self.port = kwargs['tcp_port']
        self.logger = logging.getLogger('Server {}'.format(port))
        self.port = port
        # self.conf = kwargs
        self.__stop = False
        self.clients = set()
        self.thread_accept = threading.Thread(target=SerialServer.__thread_accept_client, args=(self,))
        self.ready = threading.Event()
        self.socket = socket.socket()
        self.client_on_recv = on_tcp_receive
        self.on_client_connect = on_client_connect
        self.on_client_disconnect = on_client_disconnect
        self.lock = threading.Lock()

    def __remove_client(self, client: SerialClient):
        with self.lock:
            self.clients.remove(client)
        self.on_client_disconnect(client)

    def __thread_accept_client(self):
        self.ready.set()
        while True:
            try:
                client_socket, address=self.socket.accept()
                client = SerialClient(client_socket, address,
                                      on_disconnect=self.__remove_client,
                                      on_connect=self.on_client_connect,
                                      on_received=self.client_on_recv)
                with self.lock:
                    self.clients.add(client)
                client.start()
            except socket.timeout:
                if self.__stop:
                    return
                continue
            except Exception as e:
                self.logger.error("accept client failed: {}".format(e))

            if self.__stop:
                return
            # self._make_thread(client_socket, addr)

    def __start_accept_thread(self):
        # configure server socket
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(('', self.port))
        self.socket.listen(1)
        self.socket.settimeout(1)

        self.thread_accept.start()

    def __set_stop(self):
        self.__stop = True
        for client in self.get_clients():
            client.stop()

    def stop(self):
        self.__set_stop()
        self.thread_accept.join()
        self.socket.close()
        # while len(self.clients):
        #    time.sleep(1)
        for client in self.get_clients():
            client.thread.join()

    def get_clients(self):
        with self.lock:
            ret = set(x for x in self.clients)
        return ret

    def send_to_all(self, data):
        for client in self.get_clients():
            client.send(data)

    def run(self):
        self.logger.debug("Server: Run")
        self.__start_accept_thread()

