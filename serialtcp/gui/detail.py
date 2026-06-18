"""Detail panel (right column): console, settings, stats for one port.

Renders four states from the design: empty (no selection), running,
reconnecting, and stopped. The structure is rebuilt only when the selected
service or its status changes; live values are updated in place each tick.
"""

import tkinter as tk
from tkinter import filedialog, messagebox

from . import widgets
from .ansi import parse_ansi, clean
from .util import format_bytes, format_duration
from serialtcp.service import (
    STATUS_RUNNING, STATUS_RECONNECTING, STATUS_STOPPED,
)

_NEWLINES = {'CRLF': b'\r\n', 'LF': b'\n', 'CR': b'\r', 'none': b''}
_LINE_ENDINGS = ['CRLF', 'LF', 'CR', 'none']

_MAX_CONSOLE_LINES = 500


class DetailPanel(tk.Frame):
    def __init__(self, parent, theme, actions):
        super().__init__(parent, bg=theme.colors.panel)
        self.theme = theme
        self.actions = actions          # dict: start/stop/edit/remove -> fn(service)
        self.service = None
        self._build_key = None          # (id(service), status) currently rendered
        self._dyn = {}                  # dynamic label refs
        self._console = None            # tk.Text or None
        self._build_empty()

    # ------------------------------------------------------------- public API
    def show(self, service):
        self.service = service
        self._build_key = None          # force rebuild
        self.refresh()
        if self._console is not None and service is not None:
            self._render_buffer(service)

    def refresh(self, now=None):
        svc = self.service
        status = svc.status if svc else None
        key = (id(svc), status) if svc else None
        if key != self._build_key:
            self._rebuild(svc, status)
            self._build_key = key
            if self._console is not None and svc is not None:
                self._render_buffer(svc)
        self._update_dynamic(svc, status)

    def append_log(self, service, event):
        if service is not self.service or self._console is None:
            return
        self._append_line(event)

    # --------------------------------------------------------------- rebuild
    def _clear(self):
        for child in self.winfo_children():
            child.destroy()
        self._dyn = {}
        self._console = None

    def _rebuild(self, service, status):
        self._clear()
        if service is None:
            self._build_empty()
        elif status == STATUS_STOPPED:
            self._build_stopped(service)
        else:
            self._build_active(service, status)

    def _build_empty(self):
        c = self.theme.colors
        box = tk.Frame(self, bg=c.panel)
        box.place(relx=0.5, rely=0.5, anchor='center')
        tile = tk.Label(box, text=widgets.CHEVRON, bg=c.chip_blue_bg, fg=c.accent,
                        font=self.theme.ui(20, 700), width=2, height=1)
        tile.pack()
        tk.Label(box, text='Select a port', bg=c.panel, fg=c.text_medium2,
                 font=self.theme.ui(14, 600)).pack(pady=(14, 0))
        tk.Label(box, text='Click any port on the left to open its console, '
                           'settings and live log here.',
                 bg=c.panel, fg=c.text_muted2, font=self.theme.ui(12),
                 wraplength=240, justify='center').pack(pady=(6, 0))

    def _header(self, service, status):
        """Title + status sub-line + action buttons."""
        c = self.theme.colors
        cfg = service.config
        header = tk.Frame(self, bg=c.panel)
        header.pack(fill='x')

        left = tk.Frame(header, bg=c.panel)
        left.pack(side='left')
        title = tk.Frame(left, bg=c.panel)
        title.pack(anchor='w')
        tk.Label(title, text=cfg.label, bg=c.panel, fg=c.text_strong,
                 font=self.theme.ui(19, 700)).pack(side='left')
        tk.Label(title, text='→ {}:{}'.format(cfg.bind_host, cfg.tcp_port), bg=c.panel,
                 fg=c.text_muted, font=self.theme.mono(13, 500)).pack(side='left', padx=(10, 0))

        sub = tk.Frame(left, bg=c.panel)
        sub.pack(anchor='w', pady=(7, 0))
        dot_color = {STATUS_RUNNING: c.ok_dot, STATUS_RECONNECTING: c.warn_dot,
                     STATUS_STOPPED: c.stop_dot}[status]
        text_color = {STATUS_RUNNING: c.ok_text, STATUS_RECONNECTING: c.warn_text,
                      STATUS_STOPPED: c.stop_text}[status]
        tk.Label(sub, text=widgets.DOT, bg=c.panel, fg=dot_color,
                 font=self.theme.ui(8)).pack(side='left', padx=(0, 6))
        self._dyn['sub'] = tk.Label(sub, text='', bg=c.panel, fg=text_color,
                                    font=self.theme.ui(11.5, 600))
        self._dyn['sub'].pack(side='left')

        buttons = tk.Frame(header, bg=c.panel)
        buttons.pack(side='right')
        return buttons

    def _build_active(self, service, status):
        c = self.theme.colors
        cfg = service.config
        reconnecting = status == STATUS_RECONNECTING

        buttons = self._header(service, status)
        widgets.danger_button(buttons, self.theme, 'Stop',
                              lambda: self.actions['stop'](service),
                              glyph=widgets.SQUARE).pack(side='left', padx=(0, 8))
        widgets.light_button(buttons, self.theme, 'Edit',
                             lambda: self.actions['edit'](service)).pack(side='left')

        if reconnecting:
            banner = tk.Frame(self, bg=c.banner_bg, highlightthickness=1,
                              highlightbackground=c.banner_border,
                              highlightcolor=c.banner_border)
            banner.pack(fill='x', pady=(16, 0))
            row = tk.Frame(banner, bg=c.banner_bg)
            row.pack(fill='x', padx=13, pady=11)
            tk.Label(row, text=widgets.DOT, bg=c.banner_bg, fg=c.warn_dot,
                     font=self.theme.ui(8)).pack(side='left', padx=(0, 9))
            tk.Label(row, text='Serial device lost — TCP client kept connected, '
                              'retrying every 2s.', bg=c.banner_bg, fg=c.banner_text,
                     font=self.theme.ui(12), wraplength=560, justify='left').pack(side='left')

        # stat tiles
        grid = tk.Frame(self, bg=c.panel)
        grid.pack(fill='x', pady=(14 if reconnecting else 16, 0))
        for i in range(4):
            grid.columnconfigure(i, weight=1, uniform='tiles')
        self._dyn['clients'] = widgets.StatTile(grid, self.theme, 'TCP CLIENTS')
        self._dyn['tx'] = widgets.StatTile(grid, self.theme, 'TX TOTAL')
        self._dyn['rx'] = widgets.StatTile(grid, self.theme, 'RX TOTAL')
        baud = widgets.StatTile(grid, self.theme, 'BAUD')
        for i, tile in enumerate((self._dyn['clients'], self._dyn['tx'],
                                  self._dyn['rx'], baud)):
            tile.grid(row=0, column=i, sticky='nsew', padx=(0 if i == 0 else 10, 0))
        baud.set(str(cfg.baudrate))

        self._build_chips(self._active_chips(cfg))
        self._build_console(service, reconnecting)

    def _build_stopped(self, service):
        c = self.theme.colors
        cfg = service.config
        buttons = self._header(service, STATUS_STOPPED)
        widgets.primary_button(buttons, self.theme, 'Start',
                               lambda: self.actions['start'](service)).pack(side='left', padx=(0, 8))
        widgets.light_button(buttons, self.theme, 'Edit',
                             lambda: self.actions['edit'](service)).pack(side='left', padx=(0, 8))
        widgets.danger_button(buttons, self.theme, 'Remove',
                              lambda: self.actions['remove'](service), glyph='',
                              border=c.danger_border).pack(side='left')

        self._build_chips([
            (cfg.framing, True),
            ('{} baud'.format(cfg.baudrate), False),
            ('xon/xoff {}'.format('on' if cfg.xonxoff else 'off'), False),
        ])

        empty = tk.Frame(self, bg=c.panel, highlightthickness=1,
                         highlightbackground=c.dash2, highlightcolor=c.dash2)
        empty.pack(fill='x', pady=(16, 0))
        inner = tk.Frame(empty, bg=c.panel)
        inner.pack(pady=40, padx=24)
        tk.Label(inner, text=widgets.SQUARE, bg=c.stop_pill_bg, fg=c.stop_dot,
                 font=self.theme.ui(14), width=3, height=1).pack()
        tk.Label(inner, text='Port stopped', bg=c.panel, fg=c.stop_text,
                 font=self.theme.ui(13, 600)).pack(pady=(14, 0))
        tk.Label(inner, text='Press Start to begin listening on :{}. The serial port '
                            'opens when the first TCP client connects and closes when '
                            'the last disconnects.'.format(cfg.tcp_port),
                 bg=c.panel, fg=c.text_muted2, font=self.theme.ui(12),
                 wraplength=340, justify='center').pack(pady=(6, 0))

    # ----------------------------------------------------------------- chips
    def _active_chips(self, cfg):
        chips = [(cfg.framing, True), ('parity {}'.format(cfg.parity), True),
                 ('xon/xoff {}'.format('on' if cfg.xonxoff else 'off'), False),
                 ('char-mode {}'.format('on' if cfg.char_mode else 'off'), False)]
        if cfg.char_delay:
            chips.append(('char-delay {}s'.format(cfg.char_delay), False))
        chips.append(('echo-wait {}s'.format(cfg.wait_echo or 0), False))
        return chips

    def _build_chips(self, chips):
        c = self.theme.colors
        row = tk.Frame(self, bg=c.panel)
        row.pack(fill='x', pady=(16, 0))
        tk.Label(row, text='SERIAL', bg=c.panel, fg=c.text_muted,
                 font=self.theme.ui(11, 600)).pack(side='left', padx=(0, 8))
        for text, active in chips:
            widgets.make_chip(row, self.theme, text, active).pack(side='left', padx=(0, 8))

    # --------------------------------------------------------------- console
    def _build_console(self, service, reconnecting):
        c = self.theme.colors
        frame = tk.Frame(self, bg=c.con_bg)
        frame.pack(fill='both', expand=True, pady=(16, 0))

        head = tk.Frame(frame, bg=c.con_bg)
        head.pack(fill='x', padx=15, pady=(13, 8))
        tk.Label(head, text='CONSOLE — {}'.format(service.config.label),
                 bg=c.con_bg, fg=c.con_head, font=self.theme.ui(10, 600)).pack(side='left')
        live_text = '● retrying' if reconnecting else '● live'
        live_color = c.con_retrying if reconnecting else c.con_live
        tk.Label(head, text=live_text, bg=c.con_bg, fg=live_color,
                 font=self.theme.ui(10, 500)).pack(side='right')
        self._log_label = tk.Label(head, bg=c.con_bg, cursor='hand2',
                                   font=self.theme.ui(10, 600))
        self._log_label.pack(side='right', padx=(0, 14))
        self._log_label.bind('<Button-1>', lambda _e: self._toggle_log(service))
        self._update_log_label(service)

        text = tk.Text(frame, bg=c.con_bg, fg=c.con_rx, height=11, bd=0,
                       highlightthickness=0, wrap='char', font=self.theme.mono(11.5),
                       padx=15, pady=0, state='disabled', cursor='arrow',
                       spacing1=2, spacing3=2)
        text.pack(fill='both', expand=True)
        text.tag_configure('ts', foreground=c.con_ts)
        self._kind_color = {
            'conn': c.con_conn, 'rx': c.con_rx, 'tx': c.con_tx,
            'status': c.con_status, 'retry': c.con_retry,
        }
        self._color_tags = set()

        # Scroll the console itself on wheel and stop the event from bubbling
        # up to the sidebar list.
        def _con_wheel(event):
            delta = 1 if getattr(event, 'num', None) == 5 or event.delta < 0 else -1
            text.yview_scroll(delta, 'units')
            return 'break'
        for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            text.bind(seq, _con_wheel)
        self._console = text

        self._build_send_line(frame, service)

    def _build_send_line(self, parent, service):
        c = self.theme.colors
        bar = tk.Frame(parent, bg=c.con_bg)
        bar.pack(fill='x', padx=15, pady=(8, 13))

        self._connect_btn = tk.Label(bar, bg='#1b212c', cursor='hand2',
                                     font=self.theme.ui(11.5, 600), padx=12, pady=6)
        self._connect_btn.pack(side='left', padx=(0, 8))
        self._connect_btn.bind('<Button-1>', lambda _e: self._toggle_local(service))
        self._update_connect_label(service)

        entry = tk.Entry(bar, bg='#1b212c', fg=c.con_rx, insertbackground=c.con_status,
                         relief='flat', font=self.theme.mono(11.5),
                         highlightthickness=1, highlightbackground='#2a323f',
                         highlightcolor=c.accent)
        entry.pack(side='left', fill='x', expand=True, ipady=5, ipadx=8)

        nl_var = tk.StringVar(value=service.config.line_ending or 'CRLF')
        opt = tk.OptionMenu(bar, nl_var, *_LINE_ENDINGS)
        opt.configure(bg='#1b212c', fg=c.con_ts, activebackground='#2a323f',
                      activeforeground=c.con_rx, relief='flat', highlightthickness=0,
                      bd=0, font=self.theme.ui(10), width=4)
        opt['menu'].configure(bg='#1b212c', fg=c.con_rx)
        opt.pack(side='left', padx=(8, 0))

        def on_nl_change(*_):
            service.config.line_ending = nl_var.get()
            self.actions.get('save', lambda: None)()
        nl_var.trace_add('write', on_nl_change)

        def do_send(_e=None):
            payload = entry.get()
            if not payload:
                return
            data = payload.encode('utf-8', 'replace') + _NEWLINES.get(nl_var.get(), b'\n')
            service.send_to_serial(data)
            entry.delete(0, 'end')

        entry.bind('<Return>', do_send)
        widgets.FlatButton(bar, self.theme, 'Send', do_send, bg=c.accent, fg=c.white,
                           hover='#245fbd', size=11.5, padx=14, pady=5).pack(side='left', padx=(8, 0))

    def _update_connect_label(self, service):
        c = self.theme.colors
        if service.local_client:
            self._connect_btn.configure(text=widgets.SQUARE + ' Disconnect', fg=c.danger)
        else:
            self._connect_btn.configure(text=widgets.TRIANGLE + ' Connect', fg=c.con_live)

    def _toggle_local(self, service):
        if service.local_client:
            service.disconnect_local()
        else:
            service.connect_local()
        self._update_connect_label(service)

    def _update_log_label(self, service):
        c = self.theme.colors
        if service.logging_to_file:
            self._log_label.configure(text='⦿ logging', fg=c.con_live)
        else:
            self._log_label.configure(text='○ log', fg=c.con_head)

    def _toggle_log(self, service):
        if service.logging_to_file:
            service.stop_logging()
        else:
            path = filedialog.asksaveasfilename(
                parent=self, title='Serial log file', defaultextension='.log',
                initialfile='{}.log'.format(service.config.label),
                filetypes=[('Log files', '*.log'), ('All files', '*.*')])
            if not path:
                return
            if not service.start_logging(path):
                messagebox.showerror('Log', 'Could not open log file:\n{}'.format(path),
                                     parent=self)
                return
        self.actions.get('save', lambda: None)()
        self._update_log_label(service)

    def _render_buffer(self, service):
        text = self._console
        text.configure(state='normal')
        text.delete('1.0', 'end')
        for event in service.snapshot_log():
            self._insert_event(text, event)
        text.configure(state='disabled')
        text.see('end')

    def _append_line(self, event):
        text = self._console
        text.configure(state='normal')
        self._insert_event(text, event)
        # Trim history so the widget can't grow without bound.
        line_count = int(text.index('end-1c').split('.')[0])
        if line_count > _MAX_CONSOLE_LINES:
            text.delete('1.0', '{}.0'.format(line_count - _MAX_CONSOLE_LINES + 1))
        text.configure(state='disabled')
        text.see('end')

    def _color_tag(self, text, color):
        tag = 'fg' + color
        if tag not in self._color_tags:
            text.tag_configure(tag, foreground=color)
            self._color_tags.add(tag)
        return tag

    def _insert_event(self, text, event):
        text.insert('end', '[{}] '.format(event.ts), 'ts')
        default = self._kind_color.get(event.kind, self.theme.colors.con_rx)
        for chunk, color in parse_ansi(event.text, default):
            chunk = clean(chunk)
            if chunk:
                text.insert('end', chunk, self._color_tag(text, color))
        text.insert('end', '\n')

    # -------------------------------------------------------------- dynamic
    def _update_dynamic(self, service, status):
        if service is None:
            return
        if status == STATUS_STOPPED:
            return
        if 'sub' in self._dyn:
            if status == STATUS_RECONNECTING:
                self._dyn['sub'].configure(
                    text='Reconnecting · attempt {}'.format(service.reconnect_attempt))
            else:
                self._dyn['sub'].configure(
                    text='Running · uptime {}'.format(format_duration(service.uptime)))
        if 'clients' in self._dyn:
            self._dyn['clients'].set(str(service.client_count))
        muted = status == STATUS_RECONNECTING
        if 'tx' in self._dyn:
            if muted:
                self._dyn['tx'].set('—', muted=True)
            else:
                self._dyn['tx'].set(*format_bytes(service.tx_total))
        if 'rx' in self._dyn:
            if muted:
                self._dyn['rx'].set('—', muted=True)
            else:
                self._dyn['rx'].set(*format_bytes(service.rx_total))
