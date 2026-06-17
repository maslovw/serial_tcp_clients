"""Headless serial-to-TCP port service.

Wraps the existing :class:`~serialtcp.server.SerialServer` and
:class:`~serialtcp.serial_port.SerialPort` for a single serial -> TCP mapping
without the CLI's signal handling or blocking loop, so a GUI can own many
mappings at once and drive each one independently.

The service is thread-safe to *control* (``start``/``stop``) from the GUI
thread, and reports activity back through a single ``on_event`` callback that
fires from background I/O threads. The GUI is expected to marshal those events
onto the Tk main loop (queue + ``after``).
"""

import time
import logging
import threading
from datetime import datetime
from collections import namedtuple, deque
from dataclasses import dataclass, asdict

from serialtcp.server import SerialServer
from serialtcp.serial_port import SerialPort


# A single console log line. ``kind`` drives the colour the GUI renders:
#   conn   - TCP client connected / disconnected
#   rx     - data received from the serial device
#   tx     - data sent to the serial device
#   status - lifecycle notices (listening, serial connected, stopped)
#   retry  - reconnect attempts while the device is lost
LogEvent = namedtuple('LogEvent', 'kind text ts')

STATUS_STOPPED = 'stopped'
STATUS_RUNNING = 'running'
STATUS_RECONNECTING = 'reconnecting'

# How often the serial layer retries a lost device (matches SerialPort.timeout).
RECONNECT_INTERVAL = 2.0

# Cap a partial (newline-less) console line so binary streams can't grow it
# without bound before it is flushed to the log.
_MAX_PARTIAL_LINE = 4096

# How many recent log lines each service retains for re-rendering the console.
_LOG_HISTORY = 1000


@dataclass
class PortConfig:
    """One serial -> TCP mapping. Serialised to/from the YAML config."""
    device: str
    tcp_port: int
    name: str = ''
    baudrate: int = 115200
    parity: str = 'N'          # one of N E O S M
    xonxoff: bool = False
    char_mode: bool = False
    char_delay: float = 0.0
    wait_echo: float = 0.0
    line_ending: str = 'CRLF'    # console send newline: CRLF | LF | CR | none
    log_file: str = ''           # path to log all serial activity (empty = off)
    allow_remote: bool = False   # False -> bind 127.0.0.1, True -> bind 0.0.0.0
    autostart: bool = False

    @property
    def label(self):
        """Human label for the card/detail header."""
        return self.name or self.device or '?'

    @property
    def bind_host(self):
        """Listen address: localhost by default, all interfaces if remote-allowed."""
        return '0.0.0.0' if self.allow_remote else '127.0.0.1'

    @property
    def framing(self):
        """Serial framing chip, e.g. ``8N1`` (data bits fixed at 8/1 stop)."""
        return '8{}1'.format(self.parity)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


class PortService:
    """Runs one serial -> TCP mapping and exposes live stats + a log stream."""

    def __init__(self, config: PortConfig, on_event=None):
        self.config = config
        self._on_event = on_event or (lambda service, event: None)
        self.logger = logging.getLogger('Port {}'.format(config.tcp_port))

        self._server = None
        self._serial = None
        self._running = False
        self.started_at = None

        # Cumulative byte counters (bytes are counted at the service boundary).
        self.tx_total = 0   # bytes written to the serial device
        self.rx_total = 0   # bytes read from the serial device

        self.reconnect_attempt = 0
        self._last_retry_log = 0.0
        self._line_bufs = {}     # kind -> partial bytes awaiting a newline

        self.log_buffer = deque(maxlen=_LOG_HISTORY)
        self._log_lock = threading.Lock()
        self._log_fh = None      # open file handle when logging to disk

    # ------------------------------------------------------------------ state
    @property
    def running(self):
        return self._running

    @property
    def serial_connected(self):
        return bool(self._serial and self._serial.is_connected)

    @property
    def client_count(self):
        if not (self._server and self._running):
            return 0
        return len(self._server.get_clients())

    @property
    def status(self):
        if not self._running:
            return STATUS_STOPPED
        if self.client_count > 0 and not self.serial_connected:
            return STATUS_RECONNECTING
        return STATUS_RUNNING

    @property
    def uptime(self):
        if self.started_at is None:
            return 0.0
        return time.time() - self.started_at

    # --------------------------------------------------------------- control
    def start(self):
        """Open the TCP listener. Raises OSError if the port can't be bound."""
        if self._running:
            return
        self.tx_total = 0
        self.rx_total = 0
        self.reconnect_attempt = 0
        self._line_bufs = {}

        cfg = self.config
        self._serial = SerialPort(
            cfg.device,
            on_received=self._on_serial_receive,
            on_connect=self._on_serial_connect,
            on_disconnect=self._on_serial_disconnect,
            keep_active=True,
            baudrate=cfg.baudrate,
            parity=cfg.parity,
            xonxoff=cfg.xonxoff,
            char_mode=cfg.char_mode,
            char_delay=cfg.char_delay,
            wait_echo=cfg.wait_echo,
        )
        self._server = SerialServer(
            cfg.tcp_port,
            host=cfg.bind_host,
            on_tcp_receive=self._on_tcp_receive,
            on_client_connect=self._on_client_connect,
            on_client_disconnect=self._on_client_disconnect,
        )
        try:
            self._server.run()   # binds the socket; raises on conflict
        except Exception:
            self._server = None
            self._serial = None
            raise
        self._running = True
        self.started_at = time.time()
        if cfg.log_file:
            self._open_log(cfg.log_file)
        self._emit('status', 'listening on {}:{}'.format(cfg.bind_host, cfg.tcp_port))

    def stop(self):
        if not self._running:
            return
        self._running = False
        server, serial_port = self._server, self._serial
        try:
            if server:
                server.stop()
        finally:
            if serial_port:
                serial_port.close()
        self.started_at = None
        self.reconnect_attempt = 0
        self._emit('status', 'stopped')
        self._close_log()

    def send_to_serial(self, data: bytes):
        """Transmit bytes to the serial device (used by the console input)."""
        if not (self._running and self._serial):
            return
        self.tx_total += len(data)
        self._buffer_lines('tx', data)
        self._serial.send(data)

    def poll(self):
        """Periodic housekeeping; call ~once per second from the GUI thread."""
        if self.status != STATUS_RECONNECTING:
            return
        now = time.time()
        if now - self._last_retry_log >= RECONNECT_INTERVAL:
            self._last_retry_log = now
            self.reconnect_attempt += 1
            self._emit('retry',
                       'reconnect attempt {} ...'.format(self.reconnect_attempt))

    # ------------------------------------------------------------- callbacks
    def _on_tcp_receive(self, data):
        self.tx_total += len(data)
        self._buffer_lines('tx', data)
        if self._serial:
            self._serial.send(data)

    def _on_serial_receive(self, data):
        self.rx_total += len(data)
        self._buffer_lines('rx', data)
        if self._server:
            self._server.send_to_all(data)

    def _on_client_connect(self, client):
        self._emit('conn', 'client {} connected ({} total)'.format(
            _addr(client.address), self.client_count))
        if self._serial and not self._serial.is_connected:
            self._serial.open()

    def _on_client_disconnect(self, client):
        remaining = self.client_count
        self._emit('conn', 'client {} disconnected ({} total)'.format(
            _addr(client.address), remaining))
        if remaining == 0 and self._serial:
            self._serial.close()

    def _on_serial_connect(self):
        self.reconnect_attempt = 0
        self._emit('status', 'serial {} connected'.format(self.config.device))

    def _on_serial_disconnect(self):
        # Distinguish a normal close (last client left) from a lost device.
        if self._running and self.client_count > 0:
            self.reconnect_attempt = 0
            self._last_retry_log = time.time()
            self._emit('retry', 'serial {} disconnected'.format(self.config.device))

    # --------------------------------------------------------------- helpers
    def _buffer_lines(self, kind, data):
        """Accumulate bytes and emit one LogEvent per complete text line.

        Treats CRLF, lone CR and LF all as line breaks so consoles that
        terminate lines with ``\\r`` (e.g. some DLT/serial logs) are split
        into rows instead of one endless line.
        """
        buf = self._line_bufs.get(kind, b'') + bytes(data)
        buf = buf.replace(b'\r\n', b'\n').replace(b'\r', b'\n')
        parts = buf.split(b'\n')
        rest = parts.pop()
        for line in parts:
            text = line.decode('utf-8', 'replace')
            if text:
                self._emit(kind, text)
        if len(rest) > _MAX_PARTIAL_LINE:
            text = rest.decode('utf-8', 'replace')
            if text:
                self._emit(kind, text)
            rest = b''
        self._line_bufs[kind] = rest

    def snapshot_log(self):
        """Thread-safe copy of the retained log lines (oldest first)."""
        with self._log_lock:
            return list(self.log_buffer)

    # ------------------------------------------------------------- logging
    @property
    def logging_to_file(self):
        return self._log_fh is not None

    def start_logging(self, path):
        """Start (or switch) logging all serial activity to ``path``."""
        with self._log_lock:
            self._close_log_locked()
            ok = self._open_log_locked(path)
        if ok:
            self.config.log_file = path
            self._emit('status', 'logging to {}'.format(path))
        return ok

    def stop_logging(self):
        if self._log_fh is not None:
            self._emit('status', 'logging stopped')
        with self._log_lock:
            self._close_log_locked()
        self.config.log_file = ''

    def _open_log(self, path):
        with self._log_lock:
            return self._open_log_locked(path)

    def _open_log_locked(self, path):
        try:
            self._log_fh = open(path, 'a', encoding='utf-8')
            return True
        except OSError as exc:
            self._log_fh = None
            self.logger.error('cannot open log file %s: %s', path, exc)
            return False

    def _close_log(self):
        with self._log_lock:
            self._close_log_locked()

    def _close_log_locked(self):
        if self._log_fh is not None:
            try:
                self._log_fh.close()
            except Exception:
                pass
            self._log_fh = None

    @staticmethod
    def _log_timestamp():
        now = datetime.now()
        return now.strftime('[%d.%m.%y %H:%M:%S:') + '{:03d}]'.format(now.microsecond // 1000)

    def _emit(self, kind, text):
        ev = LogEvent(kind, text, time.strftime('%H:%M:%S'))
        with self._log_lock:
            self.log_buffer.append(ev)
            if self._log_fh is not None:
                try:
                    self._log_fh.write('{} {}\n'.format(self._log_timestamp(), text))
                    self._log_fh.flush()
                except Exception:
                    pass
        try:
            self._on_event(self, ev)
        except Exception:
            self.logger.exception('event handler failed')


def _addr(address):
    """Render a socket peer address tuple as ``host:port``."""
    try:
        return '{}:{}'.format(address[0], address[1])
    except (TypeError, IndexError):
        return str(address)
