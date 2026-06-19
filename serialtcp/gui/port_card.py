"""Master-list port card: one compact card per serial -> TCP mapping."""

import time
import tkinter as tk

from . import widgets
from .util import RateMeter, format_rate
from serialtcp.service import STATUS_RUNNING, STATUS_RECONNECTING, STATUS_STOPPED


def _bind_recursive(widget, command):
    widget.bind('<Button-1>', lambda _e: command())
    for child in widget.winfo_children():
        _bind_recursive(child, command)


class PortCard(tk.Frame):
    """Selectable card showing a port's status, throughput and client count."""

    def __init__(self, parent, theme, service, on_select, on_toggle):
        c = theme.colors
        super().__init__(parent, bg=c.white, highlightthickness=1,
                         highlightbackground=c.divider, highlightcolor=c.divider)
        self.theme = theme
        self.service = service
        self.on_select = on_select
        self.on_toggle = on_toggle
        self.selected = False
        self._detail_visible = True
        self._tx_meter = RateMeter()
        self._rx_meter = RateMeter()

        inner = tk.Frame(self, bg=c.white)
        inner.pack(fill='x', padx=14, pady=13)

        # --- header row ---
        header = tk.Frame(inner, bg=c.white)
        header.pack(fill='x')
        tk.Label(header, text=service.config.label, bg=c.white, fg=c.text_strong,
                 font=theme.ui(14, 700)).pack(side='left')
        tk.Label(header, text='→ :{}'.format(service.config.tcp_port), bg=c.white,
                 fg=c.text_muted, font=theme.mono(11.5, 500)).pack(side='left', padx=(8, 0))
        self._chevron = tk.Label(header, text=widgets.CHEVRON, bg=c.white,
                                 fg=c.chevron, font=theme.ui(15, 700))
        self._chevron.pack(side='right')
        self._pill = widgets.StatusPill(header, theme)
        self._pill.pack(side='right', padx=(0, 8))

        # --- serial connection row ---
        serial = tk.Frame(inner, bg=c.white)
        serial.pack(fill='x', pady=(8, 0))
        self._serial_dot = tk.Label(serial, text=widgets.DOT, bg=c.white,
                                    font=theme.ui(7))
        self._serial_dot.pack(side='left')
        self._serial_text = tk.Label(serial, bg=c.white, font=theme.ui(10.5, 500))
        self._serial_text.pack(side='left', padx=(5, 0))
        # Reserve the header chevron's width so the chip's right edge lines up
        # with the status pill above (which the chevron insets), not the raw edge.
        self._chevron_spacer(serial).pack(side='right')
        # serial port name chip, recoloured by link state in _set_serial
        self._port_chip = tk.Label(serial, text=service.config.device,
                                   font=theme.mono(10.5, 600), padx=9, pady=2)
        self._port_chip.pack(side='right', padx=(0, 8))

        # --- stats row ---
        stats = tk.Frame(inner, bg=c.white)
        stats.pack(fill='x', pady=(9, 0))
        self._out = self._stat_col(stats, widgets.ARROW_UP + ' OUT')
        self._out.frame.pack(side='left')
        self._in = self._stat_col(stats, widgets.ARROW_DOWN + ' IN')
        self._in.frame.pack(side='left', padx=(24, 0))

        self._chevron_spacer(stats).pack(side='right')
        clients_col = tk.Frame(stats, bg=c.white)
        clients_col.pack(side='right', padx=(0, 8))
        tk.Label(clients_col, text='CLIENTS', bg=c.white, fg=c.text_muted2,
                 font=theme.ui(9, 600)).pack(anchor='e')
        self._clients = tk.Label(clients_col, text='0', bg=c.white, fg=c.text_muted2,
                                 font=theme.ui(13, 700))
        self._clients.pack(anchor='e', pady=(4, 0))

        _bind_recursive(self, self._select)
        # The chevron toggles the detail panel instead of just selecting.
        self._chevron.bind('<Button-1>', lambda _e: self.on_toggle(self.service))
        self.refresh()

    def _stat_col(self, parent, caption):
        c = self.theme.colors
        frame = tk.Frame(parent, bg=c.white)
        tk.Label(frame, text=caption, bg=c.white, fg=c.text_muted2,
                 font=self.theme.ui(9, 600)).pack(anchor='w')
        value = tk.Label(frame, text='—', bg=c.white, fg=c.text_medium,
                         font=self.theme.mono(12, 600))
        value.pack(anchor='w', pady=(5, 0))
        col = type('Col', (), {})()
        col.frame = frame
        col.value = value
        return col

    def _chevron_spacer(self, parent):
        """Invisible label matching the header chevron, so right-aligned content
        on other rows lines up with the status pill instead of the card edge."""
        c = self.theme.colors
        return tk.Label(parent, text=widgets.CHEVRON, bg=c.white, fg=c.white,
                        font=self.theme.ui(15, 700))

    def _select(self):
        self.on_select(self.service)

    def set_state(self, selected, detail_visible):
        self.selected = selected
        self._detail_visible = detail_visible
        c = self.theme.colors
        border = c.accent if selected else c.divider
        self.configure(highlightbackground=border, highlightcolor=border)
        # The selected card points left (‹ hide) while the detail panel is open,
        # otherwise right (› show).
        glyph = widgets.CHEVRON_LEFT if (selected and detail_visible) else widgets.CHEVRON
        self._chevron.configure(text=glyph, fg=c.accent if selected else c.chevron)

    def refresh(self, now=None):
        now = time.time() if now is None else now
        c = self.theme.colors
        svc = self.service
        status = svc.status
        self._pill.set(status)
        self._set_serial(status)

        active = status == STATUS_RUNNING
        tx_rate = self._tx_meter.sample(svc.tx_total, now)
        rx_rate = self._rx_meter.sample(svc.rx_total, now)
        if active:
            self._set_rate(self._out, tx_rate)
            self._set_rate(self._in, rx_rate)
        else:
            self._set_rate(self._out, 0)
            self._set_rate(self._in, 0)

        count = svc.client_count
        self._clients.configure(text=str(count))
        if count > 0 and status == STATUS_RUNNING:
            self._clients.configure(fg=c.accent)
        elif count > 0 and status == STATUS_RECONNECTING:
            self._clients.configure(fg=c.text_medium2)
        else:
            self._clients.configure(fg=c.text_muted2)

    def _set_serial(self, status):
        """Reflect the serial device link: connected / connecting / disconnected."""
        c = self.theme.colors
        svc = self.service
        if svc.serial_connected:
            text, dot, fg = 'serial connected', c.ok_dot, c.ok_text
            chip_bg, chip_fg = c.ok_pill_bg, c.ok_text
        elif status != STATUS_STOPPED and svc.has_consumers:
            text, dot, fg = 'serial connecting…', c.warn_dot, c.warn_text
            chip_bg, chip_fg = c.warn_pill_bg, c.warn_text
        else:
            text, dot, fg = 'serial disconnected', c.stop_dot, c.text_muted2
            chip_bg, chip_fg = c.stop_pill_bg, c.stop_text
        self._serial_dot.configure(fg=dot)
        self._serial_text.configure(text=text, fg=fg)
        self._port_chip.configure(bg=chip_bg, fg=chip_fg)

    def _set_rate(self, col, rate):
        c = self.theme.colors
        text = format_rate(rate)
        col.value.configure(text=text,
                           fg=c.text_disabled if text == '—' else c.text_medium)
