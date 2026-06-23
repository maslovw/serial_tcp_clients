"""ANSI/VT escape handling for the console: SGR colours + control cleanup.

Kept tkinter-free so it can be unit tested on its own.
"""

import re

# Any ANSI/VT escape: CSI (... letter), OSC (... BEL/ST) or a bare 2-char escape.
_ANSI_RE = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b.')

# SGR foreground code -> console hex colour (tuned for the dark #11151c bg).
ANSI_COLORS = {
    30: '#5b6472', 31: '#e06c75', 32: '#9bdca0', 33: '#e6c07b',
    34: '#7fb4ff', 35: '#c678dd', 36: '#56b6c2', 37: '#c7cedb',
    90: '#7f8896', 91: '#ff7b88', 92: '#b5e8a0', 93: '#f0d59a',
    94: '#9bc7ff', 95: '#d7a3ec', 96: '#7fd0db', 97: '#ffffff',
}

# Drop C0 control chars (and DEL) except tab; ESC is consumed by _ANSI_RE first.
_CTRL = {i: None for i in range(0x20) if i != 0x09}
_CTRL[0x7f] = None


def clean(text):
    """Remove non-printable control characters (keep tab)."""
    return text.translate(_CTRL)


def parse_ansi(text, default):
    """Split ``text`` into (chunk, colour) segments, honouring SGR colours.

    Non-colour escapes (cursor moves, clears, OSC, ...) are dropped. ``default``
    is the colour used for text outside any active SGR colour.
    """
    segments = []
    pos = 0
    current = None
    for m in _ANSI_RE.finditer(text):
        if m.start() > pos:
            segments.append((text[pos:m.start()], current or default))
        seq = m.group(0)
        if seq.startswith('\x1b[') and seq.endswith('m'):
            body = seq[2:-1]
            for part in (body.split(';') if body else ['0']):
                try:
                    code = int(part) if part else 0
                except ValueError:
                    continue
                if code in (0, 39):
                    current = None
                elif code in ANSI_COLORS:
                    current = ANSI_COLORS[code]
        pos = m.end()
    if pos < len(text):
        segments.append((text[pos:], current or default))
    return segments
