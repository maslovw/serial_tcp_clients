"""Design tokens and font resolution for the Port Manager GUI.

Colours and the type scale come straight from the design handoff
(``PROMPT/design_handoff_serial_tcp_port_manager``). Tk font sizes are given
as negative numbers so they are interpreted as pixels, matching the px values
in the spec; letter-spacing and rounded corners are not expressible in Tk and
are intentionally dropped.
"""

import tkinter.font as tkfont


class Colors:
    # accent
    accent = '#2a6fdb'
    accent_text = '#2a5bb0'
    chip_blue_bg = '#eef2fb'
    # success / running
    ok_dot = '#1f8a5b'
    ok_text = '#1f7a48'
    ok_pill_bg = '#e7f6ee'
    # warning / reconnecting
    warn_dot = '#e0a020'
    warn_text = '#9a6b00'
    warn_pill_bg = '#fdf3e0'
    banner_bg = '#fdf6e8'
    banner_border = '#f4e2b8'
    banner_text = '#8a6a1a'
    # stopped / muted
    stop_dot = '#aab1bf'
    stop_text = '#7a8294'
    stop_pill_bg = '#eef0f4'
    # danger
    danger = '#b23b3b'
    danger_border = '#f0d2d2'
    # text
    text_strong = '#1d2433'
    text_medium = '#3b4252'
    text_medium2 = '#4a5263'
    text_muted = '#8a93a4'
    text_muted2 = '#9aa3b2'
    text_disabled = '#bcc3cf'
    chevron = '#c2cad6'
    # surfaces
    white = '#ffffff'
    panel = '#f6f8fb'
    sidebar = '#f6f8fb'
    chip_muted_bg = '#f3f5f8'
    # borders
    border = '#e3e6ec'
    border_soft = '#eaedf2'
    border_softer = '#eef0f4'
    divider = '#e6e9ef'
    dash = '#d3d9e2'
    dash2 = '#d8dde6'
    # console
    con_bg = '#11151c'
    con_ts = '#6b7588'
    con_rx = '#c7cedb'
    con_tx = '#e6c07b'
    con_conn = '#7fb4ff'
    con_status = '#9bdca0'
    con_retry = '#e6a87b'
    con_head = '#6b7588'
    con_live = '#4d8f6b'
    con_retrying = '#c9923a'


# Preferred monospace families, best first.
_MONO_CANDIDATES = (
    'JetBrains Mono', 'Consolas', 'Menlo', 'DejaVu Sans Mono',
    'Liberation Mono', 'Courier New', 'Courier',
)


def _weight(weight):
    """Map a CSS-ish weight (int 400..700 or str) to Tk's normal/bold."""
    if isinstance(weight, (int, float)):
        return 'bold' if weight >= 600 else 'normal'
    return weight


class Theme:
    """Resolves font families once a Tk root exists, and builds font tuples."""

    def __init__(self):
        self.colors = Colors
        try:
            self.ui_family = tkfont.nametofont('TkDefaultFont').actual('family')
        except Exception:
            self.ui_family = 'TkDefaultFont'
        self.mono_family = self._pick_mono()

    def _pick_mono(self):
        try:
            available = set(tkfont.families())
        except Exception:
            return 'Courier'
        for name in _MONO_CANDIDATES:
            if name in available:
                return name
        return 'Courier'

    def ui(self, px, weight='normal'):
        return (self.ui_family, -int(px), _weight(weight))

    def mono(self, px, weight='normal'):
        return (self.mono_family, -int(px), _weight(weight))
