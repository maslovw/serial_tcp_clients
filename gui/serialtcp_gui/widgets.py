"""Reusable themed widgets: flat buttons, status pill, stat tile, chips.

Tk has no rounded corners or drop shadows, so these reproduce the design's
*layout and colour language* with flat frames/labels and 1px highlight borders.
"""

import tkinter as tk

# Glyphs used across the UI.
TRIANGLE = '▶'   # play
SQUARE = '■'     # stop
CHEVRON = '›'    # › (expand / show detail)
CHEVRON_LEFT = '‹'  # ‹ (collapse / hide detail)
GEAR = '⚙'       # settings
PLUS = '＋'       # ＋ fullwidth plus
ARROW_UP = '▲'   # ▲
ARROW_DOWN = '▼' # ▼
DOT = '●'        # ●


def _bind_click(widget, command):
    if command is not None:
        widget.bind('<Button-1>', lambda _e: command())


class FlatButton(tk.Label):
    """A label styled and wired up as a clickable button."""

    def __init__(self, parent, theme, text='', command=None, glyph='',
                 bg=None, fg=None, border=None, hover=None, size=12.5,
                 weight=600, padx=15, pady=9):
        c = theme.colors
        bg = bg if bg is not None else c.chip_muted_bg
        fg = fg if fg is not None else c.text_medium2
        label = (glyph + '  ' + text).strip() if glyph and text else (glyph or text)
        super().__init__(parent, text=label, bg=bg, fg=fg,
                         font=theme.ui(size, weight), padx=padx, pady=pady,
                         cursor='hand2', highlightthickness=1 if border else 0,
                         highlightbackground=border or bg,
                         highlightcolor=border or bg)
        self._bg = bg
        self._hover = hover or _shade(bg)
        _bind_click(self, command)
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)

    def _on_enter(self, _e):
        self.configure(bg=self._hover)

    def _on_leave(self, _e):
        self.configure(bg=self._bg)


def primary_button(parent, theme, text, command, glyph=TRIANGLE):
    c = theme.colors
    return FlatButton(parent, theme, text, command, glyph=glyph,
                      bg=c.ok_dot, fg=c.white, hover='#1a7a4f')


def light_button(parent, theme, text, command, glyph=''):
    c = theme.colors
    return FlatButton(parent, theme, text, command, glyph=glyph,
                      bg=c.white, fg=c.text_medium2, border=c.border, hover='#f3f5f8')


def danger_button(parent, theme, text, command, glyph=SQUARE, border=None):
    c = theme.colors
    return FlatButton(parent, theme, text, command, glyph=glyph,
                      bg=c.white, fg=c.danger, border=border or c.border, hover='#fdf3f3')


def icon_button(parent, theme, glyph, command):
    c = theme.colors
    return FlatButton(parent, theme, '', command, glyph=glyph,
                      bg=c.white, fg=c.text_muted, border=c.border, hover='#f3f5f8',
                      size=15, padx=10, pady=7)


# status -> (dot, text, pill bg, label)
_STATUS = {
    'running':      ('ok_dot', 'ok_text', 'ok_pill_bg', 'Running'),
    'reconnecting': ('warn_dot', 'warn_text', 'warn_pill_bg', 'Reconnecting'),
    'stopped':      ('stop_dot', 'stop_text', 'stop_pill_bg', 'Stopped'),
}


class StatusPill(tk.Frame):
    """Rounded-ish pill with a coloured dot and status label."""

    def __init__(self, parent, theme):
        super().__init__(parent)
        self.theme = theme
        self._dot = tk.Label(self, text=DOT, font=theme.ui(8))
        self._dot.pack(side='left', padx=(8, 4), pady=2)
        self._text = tk.Label(self, font=theme.ui(10.5, 600))
        self._text.pack(side='left', padx=(0, 9), pady=2)
        self.set('stopped')

    def set(self, status):
        c = self.theme.colors
        dot, text, bg, label = _STATUS.get(status, _STATUS['stopped'])
        bg_col = getattr(c, bg)
        self.configure(bg=bg_col)
        self._dot.configure(bg=bg_col, fg=getattr(c, dot))
        self._text.configure(bg=bg_col, fg=getattr(c, text), text=label)


class StatTile(tk.Frame):
    """White bordered tile: small caption + large value (+ optional unit)."""

    def __init__(self, parent, theme, caption):
        c = theme.colors
        super().__init__(parent, bg=c.white, highlightthickness=1,
                         highlightbackground=c.border_soft, highlightcolor=c.border_soft)
        self.theme = theme
        inner = tk.Frame(self, bg=c.white)
        inner.pack(fill='x', padx=12, pady=12)
        tk.Label(inner, text=caption.upper(), bg=c.white, fg=c.text_muted2,
                 font=theme.ui(10, 600), anchor='w').pack(anchor='w')
        row = tk.Frame(inner, bg=c.white)
        row.pack(anchor='w', pady=(8, 0))
        self._value = tk.Label(row, bg=c.white, fg=c.text_strong, font=theme.ui(20, 700))
        self._value.pack(side='left')
        self._unit = tk.Label(row, bg=c.white, fg=c.text_muted2, font=theme.ui(11, 600))
        self._unit.pack(side='left', padx=(4, 0), pady=(0, 1))

    def set(self, value, unit='', muted=False):
        c = self.theme.colors
        self._value.configure(text=value,
                              fg=c.text_disabled if muted else c.text_strong)
        self._unit.configure(text=unit)


def make_chip(parent, theme, text, active=False):
    """A monospace pill chip. ``active`` chips use the blue value style."""
    c = theme.colors
    bg = c.chip_blue_bg if active else c.chip_muted_bg
    fg = c.accent_text if active else '#6b7385'
    return tk.Label(parent, text=text, bg=bg, fg=fg, font=theme.mono(11.5, 500),
                    padx=10, pady=5)


def _shade(hex_color):
    """Slightly darken a hex colour for a hover state."""
    try:
        r = int(hex_color[1:3], 16)
        g = int(hex_color[3:5], 16)
        b = int(hex_color[5:7], 16)
    except (ValueError, IndexError):
        return hex_color
    f = 0.96
    return '#{:02x}{:02x}{:02x}'.format(int(r * f), int(g * f), int(b * f))
