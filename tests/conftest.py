"""Shared fixtures for the GUI REST API / CLI tests.

``FakeApp`` implements the control surface ``serialtcp_gui.api`` expects from
``serialtcp_gui.app.App`` without any Tk, so the API (and the CLI talking to it)
can be exercised headlessly.
"""
import time
import socket

import pytest

from serialtcp.service import PortConfig, PortService
from serialtcp_gui import config as config_mod


def free_tcp_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


class FakeApp:
    """The subset of ``App`` the REST controller uses, without any Tk."""

    def __init__(self, configs=()):
        self.config_path = 'ports.yaml'
        self.log_settings = config_mod.LogSettings(file='gui.log', level='INFO')
        self.api_settings = config_mod.ApiSettings()
        self.services = [PortService(c) for c in configs]
        self.started_at = time.time()
        self.saves = 0

    @property
    def uptime(self):
        return time.time() - self.started_at

    def call_on_main(self, fn, timeout=5.0):
        return fn()

    def add_port_config(self, cfg):
        service = PortService(cfg)
        self.services.append(service)
        self.saves += 1
        return service

    def update_port_config(self, service, cfg):
        was_running = service.running
        if was_running:
            service.stop()
        service.config = cfg
        if was_running:
            service.start()
        self.saves += 1

    def remove_port_config(self, service):
        if service.running:
            service.stop()
        self.services.remove(service)
        self.saves += 1

    def start_service(self, service):
        try:
            service.start()
            return True, None
        except Exception as exc:
            return False, '{} → :{}: {}'.format(
                service.config.label, service.config.tcp_port, exc)

    def stop_service(self, service):
        service.stop()


@pytest.fixture
def app():
    """A two-mapping fake application; every mapping is stopped on teardown."""
    fake = FakeApp([PortConfig(device='COM3', tcp_port=5000, name='Console'),
                    PortConfig(device='/dev/ttyUSB0', tcp_port=5002, parity='E')])
    yield fake
    for service in list(fake.services):
        service.stop()
