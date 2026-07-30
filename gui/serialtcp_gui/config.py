"""Load and save the YAML config for the Port Manager GUI.

Config shape::

    logging:                     # optional; configures the Python logger
      file: serialtcp_gui.log    # log file path ('' or absent = no file log)
      level: INFO                # DEBUG | INFO | WARNING | ERROR | CRITICAL
    api:                         # optional; REST control interface (see api.py)
      enabled: true              # false = do not start the HTTP server
      host: 127.0.0.1            # 0.0.0.0 exposes the API on the network
      port: 410                  # HTTP listen port
    ports:
      - device: COM3
        tcp_port: 5000
        baudrate: 115200
        parity: N
        autostart: true
      - device: /dev/ttyUSB0
        tcp_port: 5002
"""

import os
import logging
import threading
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass, asdict

import yaml

from serialtcp.service import PortConfig

DEFAULT_CONFIG_NAME = 'serialtcp_ports.yaml'

# Default listen port of the REST control interface.
DEFAULT_API_PORT = 410

# Same record format the CLI uses, so file logs read consistently.
_LOG_FMT = '[%(asctime)s:%(msecs)03d]:%(name)s:%(levelname)s:%(message)s'
_LOG_DATEFMT = '%d.%m.%y %H:%M:%S'
# Rotation keeps a chatty DEBUG log from growing without bound.
_LOG_MAX_BYTES = 1_000_000
_LOG_BACKUPS = 3


@dataclass
class LogSettings:
    """Python-logger config for the GUI process (top-level ``logging`` key)."""
    file: str = ''            # path to the log file (empty = no file logging)
    level: str = 'WARNING'    # DEBUG | INFO | WARNING | ERROR | CRITICAL

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


@dataclass
class ApiSettings:
    """REST control interface config for the GUI (top-level ``api`` key).

    Binds to loopback by default so the control API is reachable only from the
    machine running the GUI; set ``host: 0.0.0.0`` to expose it on the network
    (it has no authentication).
    """
    enabled: bool = True
    host: str = '127.0.0.1'
    port: int = DEFAULT_API_PORT

    @property
    def url(self):
        """Base URL the API is served on (loopback rendered as localhost)."""
        host = 'localhost' if self.host in ('0.0.0.0', '127.0.0.1') else self.host
        return 'http://{}:{}'.format(host, self.port)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


def default_config_path():
    return os.path.join(os.getcwd(), DEFAULT_CONFIG_NAME)


def _read_yaml(path):
    if not path or not os.path.exists(path):
        return None
    with open(path, 'r') as fh:
        return yaml.safe_load(fh)


def load_configs(path):
    """Return a list of PortConfig from ``path`` (empty list if missing)."""
    data = _read_yaml(path)
    if not data:
        return []
    if isinstance(data, dict):
        ports = data.get('ports', [])
    elif isinstance(data, list):
        ports = data
    else:
        ports = []
    configs = []
    for entry in ports:
        if isinstance(entry, dict) and entry.get('device') and entry.get('tcp_port'):
            configs.append(PortConfig.from_dict(entry))
    return configs


def load_log_settings(path):
    """Return LogSettings from the top-level ``logging`` key (defaults if absent)."""
    data = _read_yaml(path)
    if isinstance(data, dict) and isinstance(data.get('logging'), dict):
        return LogSettings.from_dict(data['logging'])
    return LogSettings()


def load_api_settings(path):
    """Return ApiSettings from the top-level ``api`` key (defaults if absent)."""
    data = _read_yaml(path)
    if isinstance(data, dict) and isinstance(data.get('api'), dict):
        return ApiSettings.from_dict(data['api'])
    return ApiSettings()


def save_configs(path, configs, log_settings=None, api_settings=None):
    """Write the mappings (and, if given, logging/API settings) back to ``path``."""
    data = {}
    if log_settings is not None:
        data['logging'] = log_settings.to_dict()
    if api_settings is not None:
        data['api'] = api_settings.to_dict()
    data['ports'] = [c.to_dict() for c in configs]
    with open(path, 'w') as fh:
        yaml.safe_dump(data, fh, sort_keys=False, default_flow_style=False)


def configure_logging(settings):
    """Apply ``settings`` to the root logger.

    Sets the level and, when ``settings.file`` is given, adds a rotating file
    handler so the GUI's Python logger is captured on disk. Returns the handler
    that was installed, or None. An unopenable path is logged and skipped rather
    than crashing the app.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, str(settings.level).upper(), logging.WARNING))
    if not settings.file:
        return None
    try:
        handler = RotatingFileHandler(
            settings.file, maxBytes=_LOG_MAX_BYTES, backupCount=_LOG_BACKUPS,
            encoding='utf-8')
    except OSError as exc:
        root.warning('cannot open log file %s: %s', settings.file, exc)
        return None
    handler.setFormatter(logging.Formatter(_LOG_FMT, datefmt=_LOG_DATEFMT))
    root.addHandler(handler)
    return handler


def _thread_excepthook(args):
    """Route an uncaught exception from a background thread through logging.

    Without this, Python's default hook prints the traceback to stderr only, so
    it never reaches the configured file handler. SystemExit is ignored to match
    the default hook.
    """
    if issubclass(args.exc_type, SystemExit):
        return
    name = args.thread.name if args.thread is not None else 'unknown'
    logging.getLogger('thread').error(
        'uncaught exception in thread %s', name,
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def install_thread_excepthook():
    """Install the logging-based ``threading.excepthook`` (process-wide)."""
    threading.excepthook = _thread_excepthook
