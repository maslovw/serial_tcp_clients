"""Tests for the command-line client of the REST API (serialtcp_gui.cli).

Each test runs the real CLI ``main()`` against a real ApiServer serving the
``app`` fixture over loopback, so the whole path (argv -> HTTP -> controller ->
formatted output) is covered.
"""
import json

import pytest

pytest.importorskip('fastapi')

from serialtcp_gui import cli
from serialtcp_gui.api import ApiServer, GuiController
from serialtcp_gui.config import ApiSettings

from .conftest import free_tcp_port


@pytest.fixture
def server(app):
    settings = ApiSettings(host='127.0.0.1', port=free_tcp_port())
    api_server = ApiServer(GuiController(app), settings)
    api_server.start()
    yield settings
    api_server.stop()


@pytest.fixture
def run(server):
    """Run the CLI against the test server; returns (exit_code, stdout)."""
    def _run(*argv, capsys=None):
        return cli.main(['--url', str(server.port)] + list(argv))
    return _run


# --------------------------------------------------------------------- reads
def test_health(run, capsys):
    assert run('health') == 0
    out = capsys.readouterr().out
    assert 'Status:' in out and 'ok' in out
    assert '2 total - 0 running, 0 reconnecting, 2 stopped' in out


def test_config(run, capsys):
    assert run('config') == 0
    out = capsys.readouterr().out
    assert 'Config file:' in out
    assert 'gui.log (INFO)' in out
    assert '5000' in out and 'COM3' in out


def test_ports_table(run, capsys):
    assert run('ports') == 0
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert lines[0].split() == ['TCP', 'STATUS', 'LINK', 'DEVICE', 'BAUD', 'CLIENTS',
                                'IN', 'OUT', 'UPTIME', 'NAME']
    assert len(lines) == 3
    # a stopped mapping has no serial link to report
    assert lines[1].split()[:5] == ['5000', 'stopped', '-', 'COM3', '115200']


def test_ports_alias_list(run, capsys):
    assert run('list') == 0
    assert 'TCP' in capsys.readouterr().out


def test_show(run, capsys):
    assert run('show', '5002') == 0
    out = capsys.readouterr().out
    assert '/dev/ttyUSB0 @ 115200 8E1' in out
    assert 'Listen:' in out and '127.0.0.1:5002' in out


def test_json_output(run, capsys):
    assert run('--json', 'ports') == 0
    body = json.loads(capsys.readouterr().out)
    assert [p['tcp_port'] for p in body] == [5000, 5002]


# ----------------------------------------------------------------- mutations
def test_add_and_remove(run, app, capsys):
    assert run('add', 'COM7', '5010', '--baudrate', '9600', '--name', 'Extra') == 0
    assert 'added :5010 Extra - stopped' in capsys.readouterr().out
    assert [s.config.tcp_port for s in app.services] == [5000, 5002, 5010]
    assert app.services[2].config.baudrate == 9600

    assert run('remove', '5010') == 0
    assert 'removed' in capsys.readouterr().out
    assert [s.config.tcp_port for s in app.services] == [5000, 5002]


def test_add_with_start(run, app, capsys):
    port = free_tcp_port()
    assert run('add', 'COM7', str(port), '--start') == 0
    assert 'added :{}'.format(port) in capsys.readouterr().out
    assert app.services[2].running is True


def test_add_boolean_flags(run, app):
    assert run('add', 'COM7', '5010', '--autostart', '--no-allow-remote') == 0
    config = app.services[2].config
    assert config.autostart is True
    assert config.allow_remote is False


def test_set_changes_fields(run, app, capsys):
    assert run('set', '5000', '--baudrate', '19200', '--line-ending', 'LF') == 0
    assert 'updated :5000 Console' in capsys.readouterr().out
    assert app.services[0].config.baudrate == 19200
    assert app.services[0].config.line_ending == 'LF'


def test_set_moves_the_port(run, app):
    assert run('set', '5000', '--tcp-port', '5100') == 0
    assert app.services[0].config.tcp_port == 5100


def test_set_without_options_fails(run, capsys):
    assert run('set', '5000') == 1
    assert 'nothing to change' in capsys.readouterr().err


def test_start_and_stop_one(run, app, capsys):
    port = free_tcp_port()
    run('set', '5000', '--tcp-port', str(port))
    capsys.readouterr()

    assert run('start', str(port)) == 0
    assert 'started :{}'.format(port) in capsys.readouterr().out
    assert app.services[0].running is True

    assert run('stop', str(port)) == 0
    assert 'stopped :{}'.format(port) in capsys.readouterr().out
    assert app.services[0].running is False


def test_start_all_and_stop_all(run, app, capsys):
    for service in app.services:
        service.config.tcp_port = free_tcp_port()

    assert run('start', 'all') == 0
    assert 'started 2 mappings' in capsys.readouterr().out
    assert all(s.running for s in app.services)

    assert run('stop', 'all') == 0
    assert 'stopped 2 mappings' in capsys.readouterr().out
    assert not any(s.running for s in app.services)


# -------------------------------------------------------------------- errors
def test_unknown_mapping_reports_404(run, capsys):
    assert run('show', '9999') == 1
    err = capsys.readouterr().err
    assert '404' in err and '9999' in err


def test_duplicate_port_reports_409(run, capsys):
    assert run('add', 'COM7', '5000') == 1
    assert '409' in capsys.readouterr().err


def test_invalid_value_reports_422(run, capsys):
    assert run('add', 'COM7', '5010', '--parity', 'Z') == 1
    assert '422' in capsys.readouterr().err


def test_start_all_exit_code_on_partial_failure(run, app, capsys):
    import socket
    blocker = socket.socket()
    blocker.bind(('127.0.0.1', 0))
    blocker.listen(1)
    app.services[0].config.tcp_port = blocker.getsockname()[1]
    app.services[1].config.tcp_port = free_tcp_port()
    try:
        assert run('start', 'all') == 1
        captured = capsys.readouterr()
        assert 'Error:' in captured.err
        assert 'started 2 mappings' in captured.out
    finally:
        run('stop', 'all')
        blocker.close()


def test_unreachable_server_reports_error(capsys):
    assert cli.main(['--url', str(free_tcp_port()), 'health']) == 1
    assert 'cannot reach' in capsys.readouterr().err


def test_non_http_listener_reports_cleanly(capsys):
    """A tunnel pointing at, say, a serial console must not raise a traceback."""
    import socket
    import threading

    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)

    def echo_garbage():
        conn, _ = listener.accept()
        with conn:
            conn.recv(200)
            conn.sendall(b'not http at all\r\n')

    thread = threading.Thread(target=echo_garbage, daemon=True)
    thread.start()
    try:
        assert cli.main(['--url', str(listener.getsockname()[1]), 'health']) == 1
        err = capsys.readouterr().err
        assert 'did not answer HTTP' in err
    finally:
        thread.join(2)
        listener.close()


def test_bad_target_is_rejected(run, capsys):
    assert run('start', 'nope') == 1
    assert "expected a TCP port number or 'all'" in capsys.readouterr().err


# --------------------------------------------------------------- url resolve
def test_resolve_url_forms():
    assert cli.resolve_url('http://box:8080') == 'http://box:8080'
    assert cli.resolve_url('411') == 'http://127.0.0.1:411'
    assert cli.resolve_url('box:411') == 'http://box:411'
    assert cli.resolve_url('box') == 'http://box:410'


def test_resolve_url_from_config(tmp_path):
    path = tmp_path / 'ports.yaml'
    path.write_text('api:\n  enabled: true\n  host: 0.0.0.0\n  port: 8123\nports: []\n')
    # 0.0.0.0 is a bind address, not a destination: the client talks to loopback.
    assert cli.resolve_url(None, str(path)) == 'http://127.0.0.1:8123'


def test_resolve_url_default_without_config(tmp_path):
    assert cli.resolve_url(None, str(tmp_path / 'missing.yaml')) == cli.DEFAULT_URL
    assert cli.DEFAULT_URL == 'http://127.0.0.1:410'
