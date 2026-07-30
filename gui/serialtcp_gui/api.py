"""REST control interface for the Port Manager GUI.

A small FastAPI application, served by uvicorn in a background thread, that lets
scripts and monitoring tools drive the running GUI: check its health, read the
current configuration and the live state of every serial -> TCP mapping, add or
reconfigure mappings, and start/stop their TCP servers.

Endpoints (interactive docs at ``<base-url>/docs``, schema at ``/openapi.json``)::

    GET    /health                  liveness plus a summary of every mapping
    GET    /config                  full configuration snapshot (logging/api/ports)
    GET    /ports                   live state of every mapping
    POST   /ports                   add a mapping
    POST   /ports/start-all         start every mapping
    POST   /ports/stop-all          stop every mapping
    GET    /ports/{tcp_port}        live state of one mapping
    PATCH  /ports/{tcp_port}        change one mapping (restarted if running)
    DELETE /ports/{tcp_port}        remove a mapping
    POST   /ports/{tcp_port}/start  start one mapping's TCP server
    POST   /ports/{tcp_port}/stop   stop one mapping's TCP server

Threading
---------
uvicorn runs in its own daemon thread, so request handlers execute *off* the Tk
main loop. Read-only requests only touch plain :class:`~serialtcp.service.PortService`
attributes and are answered directly. Every request that mutates the app
(add/change/remove/start/stop) is marshalled onto the Tk main loop through
``App.call_on_main`` so that all widget mutation stays single-threaded, the same
rule the backend event queue follows. A mutation that cannot be run within
``App.call_on_main``'s timeout (a wedged main loop) is reported as HTTP 503.

Configuration and dependencies
------------------------------
The server starts only when the top-level ``api`` block in the YAML config has
``enabled: true`` (the default, on ``127.0.0.1:410``) *and* FastAPI/uvicorn are
installed::

    pip install "serial-tcp-clients-gui[api]"

Without those packages the GUI logs a warning at startup and runs exactly as
before. The API has no authentication, so it binds loopback by default; only set
``host: 0.0.0.0`` on a trusted network.
"""

import time
import socket
import logging
import threading
from typing import List, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel, Field

from serialtcp.service import (
    PortConfig, LINE_ENDINGS, STATUS_RECONNECTING, STATUS_RUNNING, STATUS_STOPPED,
)

from . import __version__
from .config import ApiSettings

_LOG = logging.getLogger(__name__)

_PARITIES = ('N', 'E', 'O', 'S', 'M')

_API_DESCRIPTION = """
Control interface of the **Serial TCP Port Manager** desktop app.

Each *mapping* shares one serial device over one TCP listen port and is
identified by that TCP port number. The serial device is opened when the first
TCP client connects and closed when the last one disconnects; starting a mapping
only opens its TCP listener.

Changes made here act exactly like the equivalent action in the GUI window and
are saved back to the app's YAML config file.
"""

_TAGS = [
    {'name': 'health', 'description': 'Liveness and a summary of the running app.'},
    {'name': 'config', 'description': 'The configuration the app is running with.'},
    {'name': 'ports', 'description': 'Inspect, configure, start and stop the serial -> TCP mappings.'},
]


# --------------------------------------------------------------------- models
class PortConfigModel(BaseModel):
    """Configuration of one serial -> TCP mapping (mirrors ``PortConfig``)."""
    device: str = Field(..., description='Serial device, e.g. COM3 or /dev/ttyUSB0.')
    tcp_port: int = Field(..., ge=1, le=65535,
                          description='TCP port clients connect to; identifies the mapping.')
    name: str = Field('', description='Optional label; defaults to the device name.')
    baudrate: int = Field(115200, ge=1, description='Serial baudrate.')
    parity: str = Field('N', description='Serial parity: N, E, O, S or M.')
    xonxoff: bool = Field(False, description='Software flow control.')
    char_mode: bool = Field(False, description='Send characters one at a time.')
    char_delay: float = Field(0.0, ge=0, description='Seconds between characters in char mode.')
    wait_echo: float = Field(0.0, ge=0, description='Seconds to wait for the echo of each character.')
    line_ending: str = Field('CRLF', description='Console send newline: CRLF, LF, CR or none.')
    log_file: str = Field('', description="Path to log all serial activity ('' = off).")
    allow_remote: bool = Field(False, description='False binds 127.0.0.1, true binds 0.0.0.0.')
    autostart: bool = Field(False, description='Start this mapping when the GUI launches.')


class PortPatchModel(BaseModel):
    """Partial update of a mapping: only the fields present are changed."""
    device: Optional[str] = None
    tcp_port: Optional[int] = Field(None, ge=1, le=65535)
    name: Optional[str] = None
    baudrate: Optional[int] = Field(None, ge=1)
    parity: Optional[str] = None
    xonxoff: Optional[bool] = None
    char_mode: Optional[bool] = None
    char_delay: Optional[float] = Field(None, ge=0)
    wait_echo: Optional[float] = Field(None, ge=0)
    line_ending: Optional[str] = None
    log_file: Optional[str] = None
    allow_remote: Optional[bool] = None
    autostart: Optional[bool] = None


class PortStateModel(BaseModel):
    """Live state of one mapping plus the configuration it runs with."""
    tcp_port: int = Field(..., description='TCP listen port; identifies the mapping.')
    label: str = Field(..., description='Name if set, otherwise the device.')
    device: str = Field(..., description='Serial device of this mapping.')
    status: str = Field(..., description='stopped | running | reconnecting.')
    running: bool = Field(..., description='True while the TCP listener is open.')
    serial_connected: bool = Field(..., description='True while the serial device is open.')
    clients: int = Field(..., description='Connected TCP clients.')
    terminal_connected: bool = Field(..., description="True if the GUI's own terminal is attached.")
    uptime_s: float = Field(..., description='Seconds since this mapping was started (0 if stopped).')
    tx_bytes: int = Field(..., description='Bytes written to the serial device since start.')
    rx_bytes: int = Field(..., description='Bytes read from the serial device since start.')
    reconnect_attempt: int = Field(..., description='Reconnect attempts since the device was lost.')
    listening_on: str = Field(..., description='host:port the TCP server binds.')
    logging_to_file: bool = Field(..., description='True while serial activity is written to log_file.')
    config: PortConfigModel


class PortSummaryModel(BaseModel):
    """How many mappings are in each state."""
    total: int
    running: int
    reconnecting: int
    stopped: int


class HealthModel(BaseModel):
    """Answer of ``GET /health``."""
    status: str = Field(..., description="'ok', or 'degraded' when a started mapping "
                                         'has lost its serial device.')
    version: str = Field(..., description='Port Manager version.')
    config_path: str = Field(..., description='YAML config file the app is using.')
    uptime_s: float = Field(..., description='Seconds since the GUI started.')
    clients: int = Field(..., description='TCP clients connected across all mappings.')
    ports: PortSummaryModel


class LogSettingsModel(BaseModel):
    """Python-logger settings of the GUI process."""
    file: str = Field(..., description="Log file path ('' = console only).")
    level: str = Field(..., description='DEBUG | INFO | WARNING | ERROR | CRITICAL.')


class ApiSettingsModel(BaseModel):
    """Settings this REST interface is running with."""
    enabled: bool
    host: str
    port: int


class ConfigModel(BaseModel):
    """Answer of ``GET /config``: everything the YAML config holds."""
    config_path: str = Field(..., description='YAML file mappings are saved to.')
    logging: LogSettingsModel
    api: ApiSettingsModel
    ports: List[PortConfigModel]


class BulkResultModel(BaseModel):
    """Answer of the start-all / stop-all endpoints."""
    ports: List[PortStateModel]
    errors: List[str] = Field([], description='One message per mapping that could not start.')


class MessageModel(BaseModel):
    detail: str


# ----------------------------------------------------------------- controller
class GuiController:
    """Bridges HTTP requests to the running :class:`~serialtcp_gui.app.App`.

    Reads go straight to the :class:`~serialtcp.service.PortService` objects
    (they touch no Tk widgets); mutations are dispatched onto the Tk main loop
    through ``App.call_on_main``. Every method raises ``HTTPException`` for
    conditions the client should see (404 unknown mapping, 409 conflict,
    422 invalid value, 503 unresponsive main loop).
    """

    def __init__(self, app):
        self._app = app

    # ------------------------------------------------------------- read-only
    def health(self):
        services = list(self._app.services)
        summary = PortSummaryModel(
            total=len(services),
            running=sum(1 for s in services if s.status == STATUS_RUNNING),
            reconnecting=sum(1 for s in services if s.status == STATUS_RECONNECTING),
            stopped=sum(1 for s in services if s.status == STATUS_STOPPED),
        )
        return HealthModel(
            status='degraded' if summary.reconnecting else 'ok',
            version=__version__,
            config_path=str(self._app.config_path),
            uptime_s=round(self._app.uptime, 3),
            clients=sum(s.client_count for s in services),
            ports=summary,
        )

    def config(self):
        return ConfigModel(
            config_path=str(self._app.config_path),
            logging=LogSettingsModel(**self._app.log_settings.to_dict()),
            api=ApiSettingsModel(**self._app.api_settings.to_dict()),
            ports=[PortConfigModel(**s.config.to_dict()) for s in self._app.services],
        )

    def port_states(self):
        return [_state(s) for s in list(self._app.services)]

    def port_state(self, tcp_port):
        return _state(self._find(tcp_port))

    # ------------------------------------------------------------- mutations
    def create_port(self, model):
        """Add a mapping. 409 if its TCP port is already mapped."""
        config = _to_config(model)

        def apply():
            if self._lookup(config.tcp_port) is not None:
                raise HTTPException(409, 'TCP port {} is already mapped'.format(config.tcp_port))
            return self._app.add_port_config(config)

        return _state(self._call(apply))

    def update_port(self, tcp_port, patch):
        """Apply a partial config change; a running mapping is restarted."""
        def apply():
            service = self._find(tcp_port)
            merged = service.config.to_dict()
            merged.update(_patch_fields(patch))
            config = _to_config(PortConfigModel(**merged))
            other = self._lookup(config.tcp_port)
            if other is not None and other is not service:
                raise HTTPException(409, 'TCP port {} is already mapped'.format(config.tcp_port))
            self._app.update_port_config(service, config)
            return service

        return _state(self._call(apply))

    def delete_port(self, tcp_port):
        """Remove a mapping, stopping it first if it is running."""
        def apply():
            self._app.remove_port_config(self._find(tcp_port))

        self._call(apply)
        return MessageModel(detail='mapping :{} removed'.format(tcp_port))

    def start_port(self, tcp_port):
        """Start one mapping's TCP server. Starting a running one is a no-op."""
        def apply():
            service = self._find(tcp_port)
            ok, err = self._app.start_service(service)
            if not ok:
                raise HTTPException(409, err)
            return service

        return _state(self._call(apply))

    def stop_port(self, tcp_port):
        """Stop one mapping's TCP server. Stopping a stopped one is a no-op."""
        def apply():
            service = self._find(tcp_port)
            self._app.stop_service(service)
            return service

        return _state(self._call(apply))

    def start_all(self):
        def apply():
            errors = []
            for service in list(self._app.services):
                ok, err = self._app.start_service(service)
                if not ok:
                    errors.append(err)
            return errors

        errors = self._call(apply)
        return BulkResultModel(ports=self.port_states(), errors=errors)

    def stop_all(self):
        def apply():
            for service in list(self._app.services):
                self._app.stop_service(service)

        self._call(apply)
        return BulkResultModel(ports=self.port_states())

    # --------------------------------------------------------------- helpers
    def _lookup(self, tcp_port):
        for service in self._app.services:
            if service.config.tcp_port == tcp_port:
                return service
        return None

    def _find(self, tcp_port):
        service = self._lookup(tcp_port)
        if service is None:
            raise HTTPException(404, 'no mapping on TCP port {}'.format(tcp_port))
        return service

    def _call(self, fn):
        """Run ``fn`` on the Tk main loop, translating a stalled loop to 503."""
        try:
            return self._app.call_on_main(fn)
        except TimeoutError as exc:
            raise HTTPException(503, 'the application did not respond: {}'.format(exc))


def _state(service):
    config = service.config
    return PortStateModel(
        tcp_port=config.tcp_port,
        label=config.label,
        device=config.device,
        status=service.status,
        running=service.running,
        serial_connected=service.serial_connected,
        clients=service.client_count,
        terminal_connected=service.local_client,
        uptime_s=round(service.uptime, 3),
        tx_bytes=service.tx_total,
        rx_bytes=service.rx_total,
        reconnect_attempt=service.reconnect_attempt,
        listening_on='{}:{}'.format(config.bind_host, config.tcp_port),
        logging_to_file=service.logging_to_file,
        config=PortConfigModel(**config.to_dict()),
    )


def _patch_fields(patch):
    """Fields set in a PATCH body (pydantic v1 and v2); explicit nulls ignored."""
    fields = (patch.model_dump(exclude_unset=True) if hasattr(patch, 'model_dump')
              else patch.dict(exclude_unset=True))
    return {key: value for key, value in fields.items() if value is not None}


def _to_config(model):
    """Validate a config payload and turn it into a PortConfig."""
    data = model.model_dump() if hasattr(model, 'model_dump') else model.dict()
    if not data['device'].strip():
        raise HTTPException(422, 'device must not be empty')
    if data['parity'] not in _PARITIES:
        raise HTTPException(422, 'parity must be one of {}'.format(', '.join(_PARITIES)))
    if data['line_ending'] not in LINE_ENDINGS:
        raise HTTPException(422, 'line_ending must be one of {}'.format(', '.join(LINE_ENDINGS)))
    data['device'] = data['device'].strip()
    return PortConfig(**data)


# ---------------------------------------------------------------- FastAPI app
def create_api(controller):
    """Build the FastAPI application served on top of ``controller``."""
    api = FastAPI(
        title='Serial TCP Port Manager API',
        description=_API_DESCRIPTION,
        version=__version__,
        openapi_tags=_TAGS,
    )

    def port_path():
        return Path(..., ge=1, le=65535, description='TCP listen port of the mapping.')

    @api.get('/health', response_model=HealthModel, tags=['health'],
             summary='Application health')
    def get_health():
        """Report that the app is alive, how long it has been up and how many
        mappings are running, reconnecting or stopped.

        ``status`` is ``ok``, or ``degraded`` while a started mapping has lost
        its serial device and is retrying.
        """
        return controller.health()

    @api.get('/config', response_model=ConfigModel, tags=['config'],
             summary='Current configuration')
    def get_config():
        """Return the configuration the app is running with: the config file
        path, the Python-logger settings, this API's settings and every serial
        -> TCP mapping."""
        return controller.config()

    @api.get('/ports', response_model=List[PortStateModel], tags=['ports'],
             summary='State of every mapping')
    def list_ports():
        """Return the live state (status, clients, throughput, uptime) and the
        configuration of every mapping."""
        return controller.port_states()

    @api.post('/ports', response_model=PortStateModel, status_code=201, tags=['ports'],
              responses={409: {'model': MessageModel, 'description': 'TCP port already mapped'}},
              summary='Add a mapping')
    def create_port(port: PortConfigModel):
        """Add a serial -> TCP mapping and save it to the config file.

        The mapping is created stopped; start it with
        ``POST /ports/{tcp_port}/start`` (``autostart`` only applies to the next
        GUI launch)."""
        return controller.create_port(port)

    @api.post('/ports/start-all', response_model=BulkResultModel, tags=['ports'],
              summary='Start every mapping')
    def start_all():
        """Start every mapping. Mappings that fail to bind are listed in
        ``errors``; the rest still start."""
        return controller.start_all()

    @api.post('/ports/stop-all', response_model=BulkResultModel, tags=['ports'],
              summary='Stop every mapping')
    def stop_all():
        """Stop every mapping, closing all TCP listeners and serial devices."""
        return controller.stop_all()

    @api.get('/ports/{tcp_port}', response_model=PortStateModel, tags=['ports'],
             responses={404: {'model': MessageModel, 'description': 'No such mapping'}},
             summary='State of one mapping')
    def get_port(tcp_port: int = port_path()):
        """Return the live state and configuration of one mapping."""
        return controller.port_state(tcp_port)

    @api.patch('/ports/{tcp_port}', response_model=PortStateModel, tags=['ports'],
               responses={404: {'model': MessageModel, 'description': 'No such mapping'},
                          409: {'model': MessageModel, 'description': 'TCP port already mapped'}},
               summary='Configure a mapping')
    def update_port(patch: PortPatchModel, tcp_port: int = port_path()):
        """Change one mapping: only the fields present in the body are applied.

        A running mapping is stopped and started again with the new settings,
        and the change is saved to the config file. ``tcp_port`` may itself be
        changed, in which case the new port identifies the mapping afterwards."""
        return controller.update_port(tcp_port, patch)

    @api.delete('/ports/{tcp_port}', response_model=MessageModel, tags=['ports'],
                responses={404: {'model': MessageModel, 'description': 'No such mapping'}},
                summary='Remove a mapping')
    def delete_port(tcp_port: int = port_path()):
        """Stop a mapping if needed, remove it and save the config file."""
        return controller.delete_port(tcp_port)

    @api.post('/ports/{tcp_port}/start', response_model=PortStateModel, tags=['ports'],
              responses={404: {'model': MessageModel, 'description': 'No such mapping'},
                         409: {'model': MessageModel, 'description': 'The TCP port could not be bound'}},
              summary='Start a mapping')
    def start_port(tcp_port: int = port_path()):
        """Open the mapping's TCP listener. Already-running mappings are left
        as they are. The serial device itself opens when the first client
        connects."""
        return controller.start_port(tcp_port)

    @api.post('/ports/{tcp_port}/stop', response_model=PortStateModel, tags=['ports'],
              responses={404: {'model': MessageModel, 'description': 'No such mapping'}},
              summary='Stop a mapping')
    def stop_port(tcp_port: int = port_path()):
        """Close the mapping's TCP listener and its serial device, dropping any
        connected clients. Already-stopped mappings are left as they are."""
        return controller.stop_port(tcp_port)

    return api


class ApiServer:
    """Runs :func:`create_api` in a uvicorn server on a background thread."""

    def __init__(self, controller, settings: ApiSettings):
        self.settings = settings
        self._api = create_api(controller)
        self._server = None
        self._thread = None

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self, timeout=5.0):
        """Bind the HTTP port and serve in a daemon thread.

        Returns once uvicorn accepts connections, so the API is usable as soon
        as the GUI window appears. Raises OSError if the port cannot be bound
        (already in use, or privileged while the process is not - note the
        default 410 is < 1024, which needs root on Linux/macOS).
        """
        if self.running:
            return
        config = uvicorn.Config(self._api, host=self.settings.host, port=self.settings.port,
                                log_config=None, access_log=False, log_level='warning')
        sock = _bind(self.settings)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._serve, args=(sock,),
                                        name='serialtcp-api', daemon=True)
        self._thread.start()

        deadline = time.time() + timeout
        while not self._server.started and self._thread.is_alive() and time.time() < deadline:
            time.sleep(0.02)
        if not self._server.started:
            if not self._thread.is_alive():
                self._server = self._thread = None
                raise OSError('the API server thread stopped during startup')
            _LOG.warning('REST API on %s is still starting up', self.settings.url)
            return
        _LOG.info('REST API listening on %s', self.settings.url)

    def _serve(self, sock):
        try:
            self._server.run(sockets=[sock])
        except Exception:
            _LOG.exception('REST API server stopped with an error')

    def stop(self, timeout=3.0):
        """Ask uvicorn to shut down and wait for the thread to finish."""
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout)
        self._server = None
        self._thread = None


def _bind(settings):
    """Bind (but do not listen on) the API's socket; uvicorn is handed the result.

    Done here rather than through ``uvicorn.Config.bind_socket`` because that
    helper turns a bind error into ``sys.exit``, losing the reason the GUI wants
    to show ("address already in use", "permission denied", ...).
    """
    family = socket.AF_INET6 if ':' in settings.host else socket.AF_INET
    sock = socket.socket(family)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((settings.host, settings.port))
    except OSError:
        sock.close()
        raise
    sock.set_inheritable(True)
    return sock
