"""Pty-free unit tests for the service line-splitting, file logging and the
tkinter-free ANSI parser. These run on every platform (incl. Windows)."""
import re

from serialtcp.service import PortConfig, PortService
from serialtcp.gui.ansi import parse_ansi, clean


def _events(data, kind='rx'):
    seen = []
    svc = PortService(PortConfig(device='X', tcp_port=1),
                      on_event=lambda s, e: seen.append((e.kind, e.text)))
    svc._buffer_lines(kind, data)
    return [text for k, text in seen]


def test_line_split_handles_cr_crlf_lf():
    assert _events(b'a\r\nb\rc\nd\n') == ['a', 'b', 'c', 'd']


def test_line_split_buffers_partial():
    seen = []
    svc = PortService(PortConfig(device='X', tcp_port=1),
                      on_event=lambda s, e: seen.append(e.text))
    svc._buffer_lines('rx', b'hel')
    svc._buffer_lines('rx', b'lo\nwor')
    assert seen == ['hello']           # 'wor' still buffered
    svc._buffer_lines('rx', b'ld\n')
    assert seen == ['hello', 'world']


def test_log_file_written_with_timestamps(tmp_path):
    path = tmp_path / 'serial.log'
    svc = PortService(PortConfig(device='X', tcp_port=1))
    assert svc.logging_to_file is False
    assert svc.start_logging(str(path)) is True
    assert svc.logging_to_file is True
    svc._buffer_lines('rx', b'hello device\n')
    svc.stop_logging()
    assert svc.logging_to_file is False

    content = path.read_text(encoding='utf-8')
    assert 'hello device' in content
    assert 'logging to' in content
    # timestamp format: [dd.mm.YY HH:MM:SS:MSEC]
    assert re.search(r'\[\d{2}\.\d{2}\.\d{2} \d{2}:\d{2}:\d{2}:\d{3}\] ', content)


def test_parse_ansi_colours():
    segs = parse_ansi('\x1b[31mred\x1b[0m plain', '#ffffff')
    assert segs == [('red', '#e06c75'), (' plain', '#ffffff')]


def test_parse_ansi_plain_text_single_segment():
    assert parse_ansi('no escapes', '#abcdef') == [('no escapes', '#abcdef')]


def test_parse_ansi_drops_non_colour_escapes():
    # cursor move + clear should be removed, leaving the text
    segs = parse_ansi('\x1b[2K\x1b[1;1Hhello', '#fff')
    assert ''.join(chunk for chunk, _ in segs) == 'hello'


def test_clean_strips_control_chars():
    assert clean('a\x07b\x00c\x08d') == 'abcd'
    assert clean('keep\ttab') == 'keep\ttab'
