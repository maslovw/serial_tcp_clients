"""Add/edit dialog for a serial -> TCP port mapping."""

import tkinter as tk
from tkinter import ttk, messagebox

from serialtcp.service import PortConfig

_BAUDRATES = ['9600', '19200', '38400', '57600', '115200', '230400', '460800', '921600']
_PARITIES = ['N', 'E', 'O', 'S', 'M']


def list_serial_devices():
    try:
        from serial.tools import list_ports
        return [p.device for p in list_ports.comports()]
    except Exception:
        return []


def open_dialog(parent, theme, existing_configs, config=None):
    """Show the modal dialog; return a PortConfig, or None if cancelled.

    ``existing_configs`` is used to reject a TCP port already in use by another
    mapping. When ``config`` is given the dialog edits it in place.
    """
    dialog = _PortDialog(parent, theme, existing_configs, config)
    parent.wait_window(dialog)
    return dialog.result


class _PortDialog(tk.Toplevel):
    def __init__(self, parent, theme, existing_configs, config):
        super().__init__(parent)
        self.theme = theme
        self.existing = existing_configs
        self.editing = config
        self.result = None
        c = theme.colors

        self.title('Edit port' if config else 'Add serial → TCP port')
        self.configure(bg=c.white)
        self.transient(parent)
        self.resizable(False, False)

        body = tk.Frame(self, bg=c.white)
        body.pack(fill='both', expand=True, padx=22, pady=20)

        # Note: not ``self._name`` — that attribute is reserved by tk widgets.
        self._name_var = tk.StringVar(value=config.name if config else '')
        self._device = tk.StringVar(value=config.device if config else '')
        self._baud = tk.StringVar(value=str(config.baudrate) if config else '115200')
        self._parity = tk.StringVar(value=config.parity if config else 'N')
        self._tcp = tk.StringVar(value=str(config.tcp_port) if config else '')
        self._xonxoff = tk.BooleanVar(value=config.xonxoff if config else False)
        self._char_mode = tk.BooleanVar(value=config.char_mode if config else False)
        self._char_delay = tk.StringVar(value=str(config.char_delay) if config else '0.0')
        self._wait_echo = tk.StringVar(value=str(config.wait_echo) if config else '0.0')
        self._allow_remote = tk.BooleanVar(value=config.allow_remote if config else False)
        self._autostart = tk.BooleanVar(value=config.autostart if config else False)

        row = self._row(body, 0)
        self._label(row, 'Name (optional)')
        tk.Entry(row, textvariable=self._name_var, width=26).pack(side='left')

        row = self._row(body, 1)
        self._label(row, 'Serial device')
        device = ttk.Combobox(row, textvariable=self._device, width=24,
                              values=list_serial_devices())
        device.pack(side='left')

        row = self._row(body, 2)
        self._label(row, 'Baudrate')
        ttk.Combobox(row, textvariable=self._baud, width=24,
                     values=_BAUDRATES).pack(side='left')

        row = self._row(body, 3)
        self._label(row, 'Parity')
        ttk.Combobox(row, textvariable=self._parity, width=24, state='readonly',
                     values=_PARITIES).pack(side='left')

        row = self._row(body, 4)
        self._label(row, 'TCP listen port')
        tk.Entry(row, textvariable=self._tcp, width=26).pack(side='left')

        row = self._row(body, 5)
        self._label(row, 'Char delay (s)')
        tk.Entry(row, textvariable=self._char_delay, width=26).pack(side='left')

        row = self._row(body, 6)
        self._label(row, 'Wait echo (s)')
        tk.Entry(row, textvariable=self._wait_echo, width=26).pack(side='left')

        checks = tk.Frame(body, bg=c.white)
        checks.grid(row=7, column=0, sticky='w', pady=(10, 0))
        tk.Checkbutton(checks, text='Software flow control (xon/xoff)',
                       variable=self._xonxoff, bg=c.white, anchor='w').pack(anchor='w')
        tk.Checkbutton(checks, text='Character-at-a-time mode',
                       variable=self._char_mode, bg=c.white, anchor='w').pack(anchor='w')
        tk.Checkbutton(checks, text='Allow remote connections (bind 0.0.0.0, not just localhost)',
                       variable=self._allow_remote, bg=c.white, anchor='w').pack(anchor='w')
        tk.Checkbutton(checks, text='Start automatically on launch',
                       variable=self._autostart, bg=c.white, anchor='w').pack(anchor='w')

        buttons = tk.Frame(body, bg=c.white)
        buttons.grid(row=8, column=0, sticky='e', pady=(18, 0))
        ttk.Button(buttons, text='Cancel', command=self._cancel).pack(side='right')
        ttk.Button(buttons, text='Save', command=self._save).pack(side='right', padx=(0, 8))

        self.bind('<Return>', lambda _e: self._save())
        self.bind('<Escape>', lambda _e: self._cancel())
        device.focus_set()
        self._center(parent)
        self.grab_set()

    def _row(self, parent, index):
        frame = tk.Frame(parent, bg=self.theme.colors.white)
        frame.grid(row=index, column=0, sticky='w', pady=5)
        return frame

    def _label(self, parent, text):
        tk.Label(parent, text=text, bg=self.theme.colors.white,
                 fg=self.theme.colors.text_medium2, font=self.theme.ui(12),
                 width=18, anchor='w').pack(side='left')

    def _center(self, parent):
        self.update_idletasks()
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            w, h = self.winfo_width(), self.winfo_height()
            self.geometry('+{}+{}'.format(px + (pw - w) // 2, py + (ph - h) // 2))
        except Exception:
            pass

    def _cancel(self):
        self.result = None
        self.destroy()

    def _save(self):
        device = self._device.get().strip()
        if not device:
            return messagebox.showerror('Invalid', 'Serial device is required.', parent=self)
        try:
            tcp_port = int(self._tcp.get())
            if not (1 <= tcp_port <= 65535):
                raise ValueError
        except ValueError:
            return messagebox.showerror('Invalid', 'TCP port must be 1–65535.', parent=self)
        for other in self.existing:
            if other is not self.editing and other.tcp_port == tcp_port:
                return messagebox.showerror(
                    'Invalid', 'TCP port {} is already used by another mapping.'.format(tcp_port),
                    parent=self)
        try:
            baudrate = int(self._baud.get())
            if baudrate <= 0:
                raise ValueError
        except ValueError:
            return messagebox.showerror('Invalid', 'Baudrate must be a positive integer.', parent=self)
        try:
            char_delay = float(self._char_delay.get() or 0)
            wait_echo = float(self._wait_echo.get() or 0)
            if char_delay < 0 or wait_echo < 0:
                raise ValueError
        except ValueError:
            return messagebox.showerror('Invalid', 'Delays must be non-negative numbers.', parent=self)

        self.result = PortConfig(
            device=device,
            tcp_port=tcp_port,
            name=self._name_var.get().strip(),
            baudrate=baudrate,
            parity=self._parity.get() or 'N',
            xonxoff=self._xonxoff.get(),
            char_mode=self._char_mode.get(),
            char_delay=char_delay,
            wait_echo=wait_echo,
            allow_remote=self._allow_remote.get(),
            autostart=self._autostart.get(),
        )
        self.destroy()
