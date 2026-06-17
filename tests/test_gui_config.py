"""Tests for the GUI's tkinter-free helpers: config I/O and formatting.

These import serialtcp.gui.config / .util only, which do not pull in tkinter,
so they run anywhere pytest does.
"""
import os
import tempfile

from serialtcp.service import PortConfig
from serialtcp.gui import config as config_mod
from serialtcp.gui.util import (
    format_bytes, format_rate, format_duration, RateMeter,
)


def test_config_roundtrip():
    cfgs = [
        PortConfig(device='COM3', tcp_port=5000, baudrate=115200, autostart=True,
                   allow_remote=True),
        PortConfig(device='/dev/ttyUSB0', tcp_port=5002, parity='E', name='Sensor'),
    ]
    path = tempfile.mktemp(suffix='.yaml')
    try:
        config_mod.save_configs(path, cfgs)
        loaded = config_mod.load_configs(path)
    finally:
        if os.path.exists(path):
            os.remove(path)

    assert [c.device for c in loaded] == ['COM3', '/dev/ttyUSB0']
    assert loaded[0].tcp_port == 5000
    assert loaded[0].autostart is True
    assert loaded[1].parity == 'E'
    assert loaded[1].label == 'Sensor'
    assert loaded[0].framing == '8N1'


def test_bind_host_default_localhost():
    local = PortConfig(device='COM3', tcp_port=5000)
    remote = PortConfig(device='COM3', tcp_port=5000, allow_remote=True)
    assert local.allow_remote is False
    assert local.bind_host == '127.0.0.1'
    assert remote.bind_host == '0.0.0.0'


def test_load_missing_returns_empty():
    assert config_mod.load_configs('/nonexistent/path.yaml') == []


def test_load_skips_incomplete_entries():
    path = tempfile.mktemp(suffix='.yaml')
    with open(path, 'w') as fh:
        fh.write('ports:\n'
                 '  - device: COM3\n'        # missing tcp_port -> skipped
                 '  - device: COM4\n'
                 '    tcp_port: 5001\n')
    try:
        loaded = config_mod.load_configs(path)
    finally:
        os.remove(path)
    assert [c.device for c in loaded] == ['COM4']


def test_format_bytes():
    assert format_bytes(0) == ('0', 'B')
    assert format_bytes(512) == ('512', 'B')
    assert format_bytes(142 * 1024) == ('142', 'KB')
    assert format_bytes(int(1.2 * 1024 * 1024)) == ('1.2', 'MB')


def test_format_rate():
    assert format_rate(0) == '—'
    assert format_rate(None) == '—'
    assert format_rate(4.2 * 1024) == '4.2 KB/s'
    assert format_rate(18 * 1024) == '18 KB/s'


def test_format_duration():
    assert format_duration(0) == '00:00:00'
    assert format_duration(3 * 3600 + 12 * 60 + 44) == '03:12:44'


def test_rate_meter():
    meter = RateMeter()
    assert meter.sample(0, 100.0) == 0.0      # first sample has no rate
    assert meter.sample(2048, 101.0) == 2048.0
    assert meter.sample(2048, 102.0) == 0.0   # no change -> zero rate
