"""About window: app icon, name, version, a short description, and source link."""

import os
import webbrowser
import tkinter as tk

from serialtcp import __version__
from . import widgets

GITHUB_URL = 'https://github.com/maslovw/serial_tcp_clients'

_DESCRIPTION = (
    'Shares a serial console (COM port) over TCP. Multiple TCP clients can '
    'connect to one serial device; the port opens on the first connection and '
    'closes on the last, with automatic reconnect if the device drops.'
)


def open_about(parent, theme, assets_dir=None):
    """Show the modal About window centred over ``parent``."""
    c = theme.colors
    win = tk.Toplevel(parent)
    win.title('About')
    win.configure(bg=c.white)
    win.transient(parent)
    win.resizable(False, False)

    body = tk.Frame(win, bg=c.white)
    body.pack(fill='both', expand=True, padx=26, pady=22)

    # app icon + title
    head = tk.Frame(body, bg=c.white)
    head.pack(anchor='w')
    _logo(head, theme, win, assets_dir).pack(side='left')
    idcol = tk.Frame(head, bg=c.white)
    idcol.pack(side='left', padx=(14, 0))
    tk.Label(idcol, text='Serial TCP Server', bg=c.white, fg=c.text_strong,
             font=theme.ui(16, 700)).pack(anchor='w')
    tk.Label(idcol, text='Port Manager · v{}'.format(__version__), bg=c.white,
             fg=c.text_muted, font=theme.ui(11.5)).pack(anchor='w', pady=(2, 0))

    tk.Label(body, text=_DESCRIPTION, bg=c.white, fg=c.text_medium2,
             font=theme.ui(12), wraplength=380, justify='left').pack(
                 anchor='w', pady=(18, 0))

    tk.Label(body, text='SOURCE', bg=c.white, fg=c.text_muted,
             font=theme.ui(10, 600)).pack(anchor='w', pady=(18, 4))
    link_base = theme.ui(11.5, 600)
    link = tk.Label(body, text=GITHUB_URL, bg=c.white, fg=c.accent, cursor='hand2',
                    font=(link_base[0], link_base[1], 'bold underline'))
    link.pack(anchor='w')
    link.bind('<Button-1>', lambda _e: webbrowser.open(GITHUB_URL))

    buttons = tk.Frame(body, bg=c.white)
    buttons.pack(anchor='e', pady=(24, 0))
    widgets.FlatButton(buttons, theme, 'Close', win.destroy, bg=c.accent,
                       fg=c.white, hover='#245fbd', size=11.5).pack(side='right')

    win.bind('<Escape>', lambda _e: win.destroy())
    _center(win, parent)
    win.grab_set()


def _logo(parent, theme, win, assets_dir):
    """The bundled app icon as the About logo; falls back to the app-bar glyph."""
    c = theme.colors
    if assets_dir:
        for name in ('icon_48.png', 'icon_64.png', 'icon_32.png'):
            path = os.path.join(assets_dir, name)
            if os.path.exists(path):
                try:
                    img = tk.PhotoImage(file=path)
                except Exception:
                    break
                win._logo_img = img      # keep a ref so Tk doesn't GC the image
                return tk.Label(parent, image=img, bg=c.white)
    return tk.Label(parent, text='⇄', bg=c.accent, fg=c.white,
                    font=theme.ui(15, 700), width=2, height=1)


def _center(win, parent):
    win.update_idletasks()
    try:
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = win.winfo_width(), win.winfo_height()
        win.geometry('+{}+{}'.format(px + (pw - w) // 2, py + (ph - h) // 2))
    except Exception:
        pass
