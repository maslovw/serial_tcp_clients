"""Integration test for serialtcp.service.PortService.

Uses a pseudo-terminal (pty) as a stand-in serial device so the full
serial <-> TCP path can be exercised headlessly. Skipped on platforms
without os.openpty (e.g. Windows).
"""
import os
import time
import socket
import threading

import pytest

openpty = getattr(os, 'openpty', None)
pytestmark = pytest.mark.skipif(openpty is None, reason='requires os.openpty')

from serialtcp.service import (
    PortConfig, PortService,
    STATUS_STOPPED, STATUS_RUNNING,
)


def _free_tcp_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait(predicate, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def pty_device():
    master_fd, slave_fd = os.openpty()
    device = os.ttyname(slave_fd)
    yield master_fd, slave_fd, device
    for fd in (master_fd, slave_fd):
        try:
            os.close(fd)
        except OSError:
            pass


def test_roundtrip(pty_device):
    master_fd, _slave_fd, device = pty_device
    events = []
    lock = threading.Lock()

    def on_event(service, ev):
        with lock:
            events.append(ev)

    cfg = PortConfig(device=device, tcp_port=_free_tcp_port(), baudrate=115200)
    service = PortService(cfg, on_event=on_event)

    assert service.status == STATUS_STOPPED
    service.start()
    try:
        assert service.status == STATUS_RUNNING
        assert service.client_count == 0

        client = socket.create_connection(('127.0.0.1', cfg.tcp_port), timeout=5)
        client.settimeout(5)

        # Serial opens once the first client connects.
        assert _wait(lambda: service.serial_connected), 'serial did not open'
        assert _wait(lambda: service.client_count == 1)

        # serial RX -> broadcast to the TCP client
        os.write(master_fd, b'hello from device\n')
        assert _wait(lambda: service.rx_total >= len(b'hello from device\n'))
        assert client.recv(64) == b'hello from device\n'

        # TCP client -> serial TX (read it back off the pty master)
        client.sendall(b'ping\n')
        assert _wait(lambda: service.tx_total >= len(b'ping\n'))
        assert _wait(lambda: os.read(master_fd, 64) == b'ping\n')

        # Closing the last client closes the serial device.
        client.close()
        assert _wait(lambda: service.client_count == 0)
        assert _wait(lambda: not service.serial_connected)
    finally:
        service.stop()

    assert service.status == STATUS_STOPPED

    kinds = {ev.kind for ev in events}
    assert 'conn' in kinds   # connect/disconnect logged
    assert 'rx' in kinds     # device output logged
    assert 'tx' in kinds     # client input logged


def test_send_to_serial(pty_device):
    master_fd, _slave_fd, device = pty_device
    cfg = PortConfig(device=device, tcp_port=_free_tcp_port())
    service = PortService(cfg)
    service.start()
    try:
        client = socket.create_connection(('127.0.0.1', cfg.tcp_port), timeout=5)
        assert _wait(lambda: service.serial_connected)

        service.send_to_serial(b'direct\n')
        assert _wait(lambda: os.read(master_fd, 64) == b'direct\n')
        assert service.tx_total >= len(b'direct\n')
        client.close()
    finally:
        service.stop()
