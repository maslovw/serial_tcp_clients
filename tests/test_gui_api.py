"""Tests for the GUI's REST control interface (serialtcp_gui.api).

They drive the FastAPI app through TestClient against the ``app`` fixture (a fake
application object implementing the same control surface as
``serialtcp_gui.app.App``), so no Tk window (and no display) is needed. Skipped
when the optional API extra (fastapi/httpx) is not installed.
"""
import socket

import pytest

fastapi = pytest.importorskip('fastapi')
pytest.importorskip('httpx')
from fastapi.testclient import TestClient

from serialtcp_gui import config as config_mod
from serialtcp_gui.api import ApiServer, GuiController, create_api

from .conftest import free_tcp_port as _free_tcp_port


@pytest.fixture
def client(app):
    with TestClient(create_api(GuiController(app))) as test_client:
        yield test_client


# ------------------------------------------------------------------- health
def test_health_ok(client):
    body = client.get('/health').json()
    assert body['status'] == 'ok'
    assert body['config_path'] == 'ports.yaml'
    assert body['clients'] == 0
    assert body['uptime_s'] >= 0
    assert body['ports'] == {'total': 2, 'running': 0, 'reconnecting': 0, 'stopped': 2}


def test_health_degraded_while_reconnecting(client, app):
    # Started, a consumer attached (the GUI terminal) but no serial device:
    # that is exactly what PortService reports as 'reconnecting'.
    service = app.services[0]
    service._running = True
    service._local_client = True
    body = client.get('/health').json()
    assert body['status'] == 'degraded'
    assert body['ports']['reconnecting'] == 1


# ------------------------------------------------------------------- config
def test_config_snapshot(client):
    body = client.get('/config').json()
    assert body['logging'] == {'file': 'gui.log', 'level': 'INFO'}
    assert body['api'] == {'enabled': True, 'host': '127.0.0.1',
                           'port': config_mod.DEFAULT_API_PORT}
    assert [p['tcp_port'] for p in body['ports']] == [5000, 5002]
    assert body['ports'][0]['device'] == 'COM3'


def test_default_api_port_is_410():
    assert config_mod.DEFAULT_API_PORT == 410
    assert config_mod.ApiSettings().port == 410


# -------------------------------------------------------------------- reads
def test_list_ports(client):
    body = client.get('/ports').json()
    assert [p['tcp_port'] for p in body] == [5000, 5002]
    first = body[0]
    assert first['label'] == 'Console'
    assert first['status'] == 'stopped'
    assert first['running'] is False
    assert first['listening_on'] == '127.0.0.1:5000'
    assert first['config']['baudrate'] == 115200


def test_get_one_port(client):
    body = client.get('/ports/5002').json()
    assert body['device'] == '/dev/ttyUSB0'
    assert body['config']['parity'] == 'E'


def test_get_unknown_port_is_404(client):
    response = client.get('/ports/9999')
    assert response.status_code == 404
    assert '9999' in response.json()['detail']


# ---------------------------------------------------------------- mutations
def test_create_port(client, app):
    response = client.post('/ports', json={'device': 'COM7', 'tcp_port': 5010,
                                           'baudrate': 921600, 'name': 'Target'})
    assert response.status_code == 201
    assert response.json()['label'] == 'Target'
    assert [s.config.tcp_port for s in app.services] == [5000, 5002, 5010]
    assert app.saves == 1


def test_create_duplicate_port_is_409(client, app):
    response = client.post('/ports', json={'device': 'COM7', 'tcp_port': 5000})
    assert response.status_code == 409
    assert len(app.services) == 2


def test_create_rejects_bad_values(client):
    assert client.post('/ports', json={'device': 'COM7', 'tcp_port': 70000}).status_code == 422
    assert client.post('/ports', json={'device': 'COM7', 'tcp_port': 5010,
                                       'parity': 'Z'}).status_code == 422
    assert client.post('/ports', json={'device': '  ', 'tcp_port': 5010}).status_code == 422
    assert client.post('/ports', json={'device': 'COM7', 'tcp_port': 5010,
                                       'line_ending': 'CRCR'}).status_code == 422


def test_patch_changes_only_given_fields(client, app):
    body = client.patch('/ports/5000', json={'baudrate': 9600, 'autostart': True}).json()
    assert body['config']['baudrate'] == 9600
    assert body['config']['autostart'] is True
    assert body['config']['device'] == 'COM3'      # untouched
    assert body['config']['name'] == 'Console'     # untouched
    assert app.services[0].config.baudrate == 9600
    assert app.saves == 1


def test_patch_ignores_explicit_nulls(client, app):
    body = client.patch('/ports/5000', json={'name': None, 'baudrate': 19200}).json()
    assert body['config']['name'] == 'Console'
    assert body['config']['baudrate'] == 19200


def test_patch_can_move_the_tcp_port(client, app):
    assert client.patch('/ports/5000', json={'tcp_port': 5100}).status_code == 200
    assert client.get('/ports/5000').status_code == 404
    assert client.get('/ports/5100').json()['device'] == 'COM3'


def test_patch_onto_used_port_is_409(client, app):
    assert client.patch('/ports/5000', json={'tcp_port': 5002}).status_code == 409
    assert app.services[0].config.tcp_port == 5000


def test_patch_unknown_port_is_404(client):
    assert client.patch('/ports/9999', json={'baudrate': 9600}).status_code == 404


def test_delete_port(client, app):
    response = client.delete('/ports/5002')
    assert response.status_code == 200
    assert 'removed' in response.json()['detail']
    assert [s.config.tcp_port for s in app.services] == [5000]


def test_delete_unknown_port_is_404(client):
    assert client.delete('/ports/9999').status_code == 404


# ------------------------------------------------------------- start / stop
def test_start_and_stop_one_port(client, app):
    port = _free_tcp_port()
    client.patch('/ports/5000', json={'tcp_port': port})

    body = client.post('/ports/{}/start'.format(port)).json()
    assert body['running'] is True
    assert body['status'] == 'running'    # listening; serial opens on first client
    assert app.services[0].running is True

    # Starting twice is a no-op, not an error.
    assert client.post('/ports/{}/start'.format(port)).status_code == 200

    body = client.post('/ports/{}/stop'.format(port)).json()
    assert body['running'] is False
    assert body['status'] == 'stopped'


def test_start_reports_bind_conflict_as_409(client, app):
    blocker = socket.socket()
    blocker.bind(('127.0.0.1', 0))
    blocker.listen(1)
    port = blocker.getsockname()[1]
    try:
        client.patch('/ports/5000', json={'tcp_port': port})
        response = client.post('/ports/{}/start'.format(port))
        assert response.status_code == 409
        assert str(port) in response.json()['detail']
    finally:
        blocker.close()


def test_start_all_and_stop_all(client, app):
    for service in app.services:
        service.config.tcp_port = _free_tcp_port()

    body = client.post('/ports/start-all').json()
    assert body['errors'] == []
    assert all(p['running'] for p in body['ports'])

    body = client.post('/ports/stop-all').json()
    assert not any(p['running'] for p in body['ports'])


def test_start_all_reports_per_port_errors(client, app):
    blocker = socket.socket()
    blocker.bind(('127.0.0.1', 0))
    blocker.listen(1)
    app.services[0].config.tcp_port = blocker.getsockname()[1]
    app.services[1].config.tcp_port = _free_tcp_port()
    try:
        body = client.post('/ports/start-all').json()
        assert len(body['errors']) == 1
        assert body['ports'][1]['running'] is True
    finally:
        client.post('/ports/stop-all')
        blocker.close()


# ------------------------------------------------------------ main loop seam
def test_stalled_main_loop_is_503(app):
    def stalled(fn, timeout=5.0):
        raise TimeoutError('main loop did not run the call within 5.0s')

    app.call_on_main = stalled
    with TestClient(create_api(GuiController(app))) as client:
        response = client.post('/ports/5000/stop')
        assert response.status_code == 503
        assert 'did not respond' in response.json()['detail']
        # Reads do not need the main loop, so they still work.
        assert client.get('/health').status_code == 200


# -------------------------------------------------------------- http server
def test_api_server_serves_requests(app):
    import json
    import urllib.request

    settings = config_mod.ApiSettings(host='127.0.0.1', port=_free_tcp_port())
    server = ApiServer(GuiController(app), settings)
    server.start()
    try:
        assert server.running
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open('http://127.0.0.1:{}/health'.format(settings.port), timeout=5) as resp:
            body = json.loads(resp.read())
        assert body['status'] == 'ok'
        assert body['ports']['total'] == 2
    finally:
        server.stop()
    assert not server.running


def test_api_server_bind_conflict_raises(app):
    blocker = socket.socket()
    blocker.bind(('127.0.0.1', 0))
    settings = config_mod.ApiSettings(host='127.0.0.1', port=blocker.getsockname()[1])
    server = ApiServer(GuiController(app), settings)
    try:
        with pytest.raises(OSError):
            server.start()
        assert not server.running
    finally:
        server.stop()
        blocker.close()


def test_openapi_documents_every_endpoint(client):
    paths = client.get('/openapi.json').json()['paths']
    assert set(paths) == {'/health', '/config', '/ports', '/ports/start-all',
                          '/ports/stop-all', '/ports/{tcp_port}',
                          '/ports/{tcp_port}/start', '/ports/{tcp_port}/stop'}
    # every operation carries a summary and a description for /docs
    for path, methods in paths.items():
        for method, spec in methods.items():
            assert spec.get('summary'), (path, method)
            assert spec.get('description'), (path, method)
