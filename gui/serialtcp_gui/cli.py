"""Command-line client for the Port Manager REST API (see :mod:`serialtcp_gui.api`).

The counterpart of the GUI's HTTP control interface: everything the API exposes
is reachable as a subcommand, so a running Port Manager can be inspected and
driven from a shell or a script without hand-writing curl calls::

    serial-tcp-ctl health                  # alive? how many mappings, how many clients
    serial-tcp-ctl ports                    # one table row per mapping
    serial-tcp-ctl show 5000                # everything about one mapping
    serial-tcp-ctl config                   # config file, logging, api, mappings
    serial-tcp-ctl add COM103 5000 --baudrate 921600 --name Target --start
    serial-tcp-ctl set 5000 --baudrate 115200
    serial-tcp-ctl start 5000               # or: start all
    serial-tcp-ctl stop 5000                # or: stop all
    serial-tcp-ctl remove 5000

Mappings are addressed by their TCP listen port, exactly as in the API.

The target defaults to the ``api`` block of the YAML config in the working
directory (``./serialtcp_ports.yaml``, or ``-c``), falling back to
``http://127.0.0.1:410``. ``--url`` overrides it and accepts a port (``411``),
``host:port`` or a full URL. ``--json`` prints the raw API response instead of
the formatted output and ``-v`` traces the HTTP exchange.

Exit status: 0 success, 1 request/connection error, 2 bad usage.

Only the standard library is used, so this client works without the ``[api]``
extra installed - that extra is only needed by the GUI process serving the API.
"""

import os
import sys
import json
import argparse
import http.client
import urllib.error
import urllib.request

from . import __version__
from .config import DEFAULT_API_PORT, default_config_path, load_api_settings
from .util import format_bytes, format_duration

# Never route localhost calls through a proxy from the environment.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))

DEFAULT_URL = 'http://127.0.0.1:{}'.format(DEFAULT_API_PORT)

# Config fields settable by `add` / `set`; ('flag', type) keyed by API field name.
_BOOL_FIELDS = ('xonxoff', 'char_mode', 'allow_remote', 'autostart')
_VALUE_FIELDS = (
    ('name', str, 'label shown on the card (defaults to the device)'),
    ('baudrate', int, 'serial baudrate'),
    ('parity', str, 'serial parity: N, E, O, S or M'),
    ('char-delay', float, 'seconds between characters in char mode'),
    ('wait-echo', float, 'seconds to wait for the echo of each character'),
    ('line-ending', str, 'console send newline: CRLF, LF, CR or none'),
    ('log-file', str, 'file to log all serial activity to'),
)


class ApiError(Exception):
    """A request failed; the message is ready to print."""


class Client:
    """Tiny JSON/HTTP client for the Port Manager API."""

    def __init__(self, url, timeout=10.0, verbose=False):
        self.url = url.rstrip('/')
        self.timeout = timeout
        self.verbose = verbose

    def get(self, path):
        return self.request('GET', path)

    def post(self, path, payload=None):
        return self.request('POST', path, payload)

    def patch(self, path, payload):
        return self.request('PATCH', path, payload)

    def delete(self, path):
        return self.request('DELETE', path)

    def request(self, method, path, payload=None):
        url = self.url + path
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header('Accept', 'application/json')
        if data:
            request.add_header('Content-Type', 'application/json')
        if self.verbose:
            print('>>> {} {}'.format(method, url), file=sys.stderr)
            if payload is not None:
                print('    {}'.format(json.dumps(payload)), file=sys.stderr)
        try:
            with _OPENER.open(request, timeout=self.timeout) as response:
                body = response.read().decode('utf-8', 'replace')
                if self.verbose:
                    print('<<< {} {}'.format(response.status, body), file=sys.stderr)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode('utf-8', 'replace') if exc.fp else ''
            if self.verbose:
                print('<<< {} {}'.format(exc.code, body), file=sys.stderr)
            raise ApiError('{} - {}'.format(exc.code, _error_detail(exc.code, body)))
        except urllib.error.URLError as exc:
            raise ApiError('cannot reach {} ({}). Is the Port Manager running '
                           'with api.enabled?'.format(self.url, exc.reason))
        except http.client.HTTPException as exc:
            # Not an HTTP server at all - e.g. a tunnel pointing at a serial
            # console, or a forward whose far end went away mid-reply.
            raise ApiError('{} did not answer HTTP ({}). Is something other than '
                           'the Port Manager API listening there?'.format(
                               self.url, type(exc).__name__))
        except OSError as exc:                       # timeout, reset, ...
            raise ApiError('request to {} failed: {}'.format(url, exc))
        if not body:
            return None
        try:
            return json.loads(body)
        except ValueError:
            raise ApiError('{} returned a non-JSON response: {!r}'.format(url, body[:80]))


def _error_detail(code, body):
    """Human-readable ``detail`` of an API error response."""
    try:
        detail = json.loads(body).get('detail', body)
    except ValueError:
        return body.strip() or 'HTTP {}'.format(code)
    if isinstance(detail, list):        # pydantic validation errors
        return '; '.join('{}: {}'.format('.'.join(str(p) for p in item.get('loc', [])[1:]),
                                         item.get('msg', '')) for item in detail)
    return str(detail)


# ------------------------------------------------------------------ formatting
def _table(headers, rows):
    """Render aligned columns; every cell is stringified."""
    rows = [[str(cell) for cell in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in rows:
        widths = [max(w, len(cell)) for w, cell in zip(widths, row)]
    lines = ['  '.join(h.ljust(w) for h, w in zip(headers, widths)).rstrip()]
    for row in rows:
        lines.append('  '.join(cell.ljust(w) for cell, w in zip(row, widths)).rstrip())
    return '\n'.join(lines)


def _bytes(n):
    value, unit = format_bytes(n)
    return '{} {}'.format(value, unit)


def _framing(config):
    return '8{}1'.format(config.get('parity', 'N'))


def _link(state):
    """Serial link state; a stopped mapping has no link to report."""
    if not state['running']:
        return '-'
    return 'up' if state['serial_connected'] else 'down'


def _print_health(body):
    ports = body['ports']
    print(_pairs([
        ('Status', body['status']),
        ('Version', body['version']),
        ('Uptime', format_duration(body['uptime_s'])),
        ('Config', body['config_path']),
        ('Mappings', '{} total - {} running, {} reconnecting, {} stopped'.format(
            ports['total'], ports['running'], ports['reconnecting'], ports['stopped'])),
        ('Clients', body['clients']),
    ]))


def _print_config(body):
    log = body['logging']
    api = body['api']
    print(_pairs([
        ('Config file', body['config_path']),
        ('Logging', '{} ({})'.format(log['file'] or 'console only', log['level'])),
        ('API', '{}:{} ({})'.format(api['host'], api['port'],
                                    'enabled' if api['enabled'] else 'disabled')),
    ]))
    print()
    if not body['ports']:
        print('No mappings configured.')
        return
    print(_table(
        ['TCP', 'NAME', 'DEVICE', 'BAUD', 'FRAMING', 'NEWLINE', 'AUTOSTART', 'REMOTE', 'LOG FILE'],
        [[c['tcp_port'], c['name'] or '-', c['device'], c['baudrate'], _framing(c),
          c['line_ending'], _yesno(c['autostart']), _yesno(c['allow_remote']),
          c['log_file'] or '-'] for c in body['ports']]))


def _print_states(states):
    if not states:
        print('No mappings configured.')
        return
    print(_table(
        ['TCP', 'STATUS', 'LINK', 'DEVICE', 'BAUD', 'CLIENTS', 'IN', 'OUT', 'UPTIME', 'NAME'],
        [[s['tcp_port'], s['status'], _link(s), s['device'], s['config']['baudrate'],
          s['clients'], _bytes(s['rx_bytes']), _bytes(s['tx_bytes']),
          format_duration(s['uptime_s']), s['config']['name'] or '-'] for s in states]))


def _print_state(state):
    config = state['config']
    clients = str(state['clients'])
    if state['terminal_connected']:
        clients += ' (+ GUI terminal)'
    print(_pairs([
        ('Mapping', '{} (:{})'.format(state['label'], state['tcp_port'])),
        ('Device', '{} @ {} {}'.format(state['device'], config['baudrate'], _framing(config))),
        ('Status', '{} (serial link {})'.format(state['status'], _link(state))
         if state['running'] else state['status']),
        ('Listen', state['listening_on']),
        ('Clients', clients),
        ('Uptime', format_duration(state['uptime_s'])),
        ('Traffic', 'in {} / out {}'.format(_bytes(state['rx_bytes']), _bytes(state['tx_bytes']))),
        ('Reconnects', state['reconnect_attempt']),
        ('Serial log', config['log_file'] + (' (active)' if state['logging_to_file'] else '')
         if config['log_file'] else 'off'),
        ('Newline', config['line_ending']),
        ('Autostart', _yesno(config['autostart'])),
        ('Flow', 'xonxoff={} char_mode={} char_delay={} wait_echo={}'.format(
            _yesno(config['xonxoff']), _yesno(config['char_mode']),
            config['char_delay'], config['wait_echo'])),
    ]))


def _pairs(items):
    width = max(len(label) for label, _ in items) + 1
    return '\n'.join('{}{}'.format((label + ':').ljust(width + 1), value)
                     for label, value in items)


def _yesno(value):
    return 'yes' if value else 'no'


def _one_line(state):
    if not state['running']:
        return ':{} {} - {}'.format(state['tcp_port'], state['label'], state['status'])
    return ':{} {} - {} (serial link {}, {} client{})'.format(
        state['tcp_port'], state['label'], state['status'], _link(state),
        state['clients'], '' if state['clients'] == 1 else 's')


# -------------------------------------------------------------------- commands
def cmd_health(client, args):
    body = client.get('/health')
    _emit(args, body, lambda: _print_health(body))
    return 0


def cmd_config(client, args):
    body = client.get('/config')
    _emit(args, body, lambda: _print_config(body))
    return 0


def cmd_ports(client, args):
    body = client.get('/ports')
    _emit(args, body, lambda: _print_states(body))
    return 0


def cmd_show(client, args):
    body = client.get('/ports/{}'.format(args.tcp_port))
    _emit(args, body, lambda: _print_state(body))
    return 0


def cmd_add(client, args):
    payload = _config_fields(args)
    payload['device'] = args.device
    payload['tcp_port'] = args.tcp_port
    body = client.post('/ports', payload)
    if args.start:
        body = client.post('/ports/{}/start'.format(body['tcp_port']))
    _emit(args, body, lambda: print('added ' + _one_line(body)))
    return 0


def cmd_set(client, args):
    payload = _config_fields(args)
    if args.tcp_port_new is not None:
        payload['tcp_port'] = args.tcp_port_new
    if not payload:
        raise ApiError('nothing to change; pass at least one option '
                       '(see: serial-tcp-ctl set --help)')
    body = client.patch('/ports/{}'.format(args.tcp_port), payload)
    _emit(args, body, lambda: print('updated ' + _one_line(body)))
    return 0


def cmd_remove(client, args):
    body = client.delete('/ports/{}'.format(args.tcp_port))
    _emit(args, body, lambda: print(body['detail']))
    return 0


def cmd_start(client, args):
    if args.target == 'all':
        body = client.post('/ports/start-all')
        _emit(args, body, lambda: _print_bulk(body, 'started'))
        return 1 if body['errors'] else 0
    body = client.post('/ports/{}/start'.format(_port_arg(args.target)))
    _emit(args, body, lambda: print('started ' + _one_line(body)))
    return 0


def cmd_stop(client, args):
    if args.target == 'all':
        body = client.post('/ports/stop-all')
        _emit(args, body, lambda: _print_bulk(body, 'stopped'))
        return 0
    body = client.post('/ports/{}/stop'.format(_port_arg(args.target)))
    _emit(args, body, lambda: print('stopped ' + _one_line(body)))
    return 0


def _print_bulk(body, verb):
    for error in body['errors']:
        print('Error: {}'.format(error), file=sys.stderr)
    print('{} {} mapping{}'.format(verb, len(body['ports']),
                                   '' if len(body['ports']) == 1 else 's'))
    _print_states(body['ports'])


def _emit(args, body, render):
    if args.json:
        print(json.dumps(body, indent=2))
    else:
        render()


def _port_arg(value):
    try:
        port = int(value)
    except (TypeError, ValueError):
        raise ApiError("expected a TCP port number or 'all', got {!r}".format(value))
    if not 1 <= port <= 65535:
        raise ApiError('TCP port must be 1-65535, got {}'.format(port))
    return port


def _config_fields(args):
    """Collect the config options actually given on the command line."""
    payload = {}
    for flag, _type, _help in _VALUE_FIELDS:
        field = flag.replace('-', '_')
        value = getattr(args, field, None)
        if value is not None:
            payload[field] = value
    for field in _BOOL_FIELDS:
        value = getattr(args, field, None)
        if value is not None:
            payload[field] = value
    return payload


# ----------------------------------------------------------------- entry point
def _add_config_options(parser):
    """Add the shared mapping-configuration options to ``add`` / ``set``."""
    for flag, type_, help_text in _VALUE_FIELDS:
        parser.add_argument('--' + flag, type=type_, default=None, help=help_text)
    for field in _BOOL_FIELDS:
        flag = field.replace('_', '-')
        parser.add_argument('--' + flag, action=argparse.BooleanOptionalAction,
                            default=None, help='set {} (--no-{} to clear)'.format(field, flag))


def build_parser():
    parser = argparse.ArgumentParser(
        prog='serial-tcp-ctl',
        description='Control a running Serial TCP Port Manager through its REST API.',
        epilog='Mappings are addressed by their TCP listen port. '
               'Use --json for raw API responses.')
    parser.add_argument('--url', help='API base URL, "host:port" or just a port '
                                      '(default: from the config file, else {})'.format(DEFAULT_URL))
    parser.add_argument('-c', '--config', help='YAML config file to read the api block from '
                                               '(default: ./serialtcp_ports.yaml)')
    parser.add_argument('--timeout', type=float, default=10.0,
                        help='request timeout in seconds (default: 10)')
    parser.add_argument('--json', action='store_true', help='print the raw JSON response')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='trace HTTP requests and responses on stderr')
    parser.add_argument('--version', action='version', version='serial-tcp-ctl ' + __version__)

    subs = parser.add_subparsers(dest='command', required=True, metavar='command')

    subs.add_parser('health', help='application health and mapping counts').set_defaults(
        func=cmd_health)
    subs.add_parser('config', help='configuration the app is running with').set_defaults(
        func=cmd_config)
    ports = subs.add_parser('ports', aliases=['list'], help='state of every mapping')
    ports.set_defaults(func=cmd_ports)

    show = subs.add_parser('show', help='state of one mapping')
    show.add_argument('tcp_port', type=int, help='TCP listen port of the mapping')
    show.set_defaults(func=cmd_show)

    add = subs.add_parser('add', help='add a mapping')
    add.add_argument('device', help='serial device, e.g. COM3 or /dev/ttyUSB0')
    add.add_argument('tcp_port', type=int, help='TCP port clients will connect to')
    add.add_argument('--start', action='store_true', help='start it right away')
    _add_config_options(add)
    add.set_defaults(func=cmd_add)

    change = subs.add_parser('set', help='change a mapping (restarted if running)')
    change.add_argument('tcp_port', type=int, help='TCP listen port of the mapping')
    change.add_argument('--tcp-port', dest='tcp_port_new', type=int, default=None,
                        help='move the mapping to another TCP port')
    _add_config_options(change)
    change.set_defaults(func=cmd_set)

    remove = subs.add_parser('remove', aliases=['rm'], help='stop and remove a mapping')
    remove.add_argument('tcp_port', type=int, help='TCP listen port of the mapping')
    remove.set_defaults(func=cmd_remove)

    start = subs.add_parser('start', help="start one mapping, or 'all'")
    start.add_argument('target', help="TCP listen port, or 'all'")
    start.set_defaults(func=cmd_start)

    stop = subs.add_parser('stop', help="stop one mapping, or 'all'")
    stop.add_argument('target', help="TCP listen port, or 'all'")
    stop.set_defaults(func=cmd_stop)

    return parser


def resolve_url(url=None, config_path=None):
    """Pick the API base URL: ``--url``, then the config file, then the default.

    ``url`` may be a full URL, ``host:port``, ``host`` or just a port number.
    """
    if not url:
        path = config_path or default_config_path()
        if os.path.exists(path):
            settings = load_api_settings(path)
            host = '127.0.0.1' if settings.host == '0.0.0.0' else settings.host
            return 'http://{}:{}'.format(host, settings.port)
        return DEFAULT_URL
    if '://' in url:
        return url
    if url.isdigit():
        return 'http://127.0.0.1:{}'.format(url)
    if ':' not in url:
        url += ':{}'.format(DEFAULT_API_PORT)
    return 'http://' + url


def main(argv=None):
    args = build_parser().parse_args(argv)
    client = Client(resolve_url(args.url, args.config), args.timeout, args.verbose)
    try:
        return args.func(client, args)
    except ApiError as exc:
        print('Error: {}'.format(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 1


if __name__ == '__main__':
    sys.exit(main())
