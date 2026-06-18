"""Port Manager application: app bar, master list, detail panel, event loop.

One window owns many :class:`~serialtcp.service.PortService` instances. Backend
I/O threads report activity through a queue that is drained on the Tk main loop
(``after``), so all widget mutation stays single-threaded.
"""

import os
import sys
import queue
import tkinter as tk
from tkinter import ttk, messagebox

from serialtcp import __version__
from . import config as config_mod
from . import widgets
from .theme import Theme
from .port_card import PortCard
from .detail import DetailPanel
from .dialog import open_dialog
from serialtcp.service import PortService

# Loop cadence: drain the event queue often; refresh stats once per second.
_TICK_MS = 200
_REFRESH_EVERY = 5   # ticks between stat refreshes (5 * 200ms = 1s)
_COLLAPSED_WIDTH = 358   # window width when the detail panel is hidden

def _assets_dir():
    # In a PyInstaller bundle data files are extracted under sys._MEIPASS;
    # otherwise they sit next to this module.
    base = getattr(sys, '_MEIPASS', None)
    if base:
        return os.path.join(base, 'serialtcp', 'gui', 'assets')
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets')


_ASSETS = _assets_dir()


def _set_taskbar_app_id():
    """On Windows, group the app under its own taskbar icon (not python's)."""
    if os.name == 'nt':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                'maslovw.serialtcp.portmanager')
        except Exception:
            pass


def _icon_debug(msg):
    if os.environ.get('SERIALTCP_ICON_DEBUG'):
        import tempfile
        try:
            with open(os.path.join(tempfile.gettempdir(), 'icon_debug.log'), 'a') as fh:
                fh.write(msg + '\n')
        except Exception:
            pass


def _apply_window_icon(root):
    """Set the window/taskbar icon from the bundled assets. Returns kept refs."""
    _icon_debug('assets={} isdir={}'.format(_ASSETS, os.path.isdir(_ASSETS)))
    images = []
    for name in ('icon_256.png', 'icon_128.png', 'icon_64.png', 'icon_48.png',
                 'icon_32.png', 'icon_16.png'):
        path = os.path.join(_ASSETS, name)
        if os.path.exists(path):
            try:
                images.append(tk.PhotoImage(file=path))
            except Exception as exc:
                _icon_debug('PhotoImage fail {}: {!r}'.format(name, exc))
    _icon_debug('images={}'.format(len(images)))
    if images:
        try:
            root.iconphoto(True, *images)
            _icon_debug('iconphoto ok')
        except Exception as exc:
            _icon_debug('iconphoto fail: {!r}'.format(exc))
    if os.name == 'nt':
        ico = os.path.join(_ASSETS, 'app.ico')
        if os.path.exists(ico):
            try:
                root.iconbitmap(default=ico)
                _icon_debug('iconbitmap ok')
            except Exception as exc:
                _icon_debug('iconbitmap fail: {!r}'.format(exc))
        else:
            _icon_debug('ico missing {}'.format(ico))
    return images


class App:
    def __init__(self, config_path):
        self.config_path = config_path
        _set_taskbar_app_id()
        self.root = tk.Tk()
        self.root.title('Serial TCP Server v{}'.format(__version__))
        self._icon_images = _apply_window_icon(self.root)
        self.root.geometry('{}x730'.format(_COLLAPSED_WIDTH))   # detail hidden by default
        self.root.minsize(330, 400)

        self.theme = Theme()
        self.events = queue.Queue()
        self.services = []
        self.cards = []
        self.selected = None
        self._detail_visible = False
        self._expanded_width = 1040
        self._tick_count = 0

        self.root.configure(bg=self.theme.colors.panel)
        self._build_appbar()
        self._build_body()

        self._load()
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.root.after(_TICK_MS, self._tick)

    # --------------------------------------------------------------- run
    def run(self):
        self.root.mainloop()

    # ------------------------------------------------------------ layout
    def _build_appbar(self):
        c = self.theme.colors
        bar = tk.Frame(self.root, bg=c.white)
        bar.pack(side='top', fill='x')
        tk.Frame(self.root, bg=c.border_softer, height=1).pack(side='top', fill='x')

        inner = tk.Frame(bar, bg=c.white)
        inner.pack(fill='x', padx=16, pady=12)

        tk.Label(inner, text='⇄', bg=c.accent, fg=c.white, font=self.theme.ui(15, 700),
                 width=2, height=1).pack(side='left')
        idcol = tk.Frame(inner, bg=c.white)
        idcol.pack(side='left', padx=(13, 0))
        tk.Label(idcol, text='Port Manager', bg=c.white, fg=c.text_strong,
                 font=self.theme.ui(16, 700)).pack(anchor='w')
        self._summary = tk.Label(idcol, text='', bg=c.white, fg=c.text_muted,
                                 font=self.theme.ui(11.5))
        self._summary.pack(anchor='w', pady=(3, 0))

        right = tk.Frame(inner, bg=c.white)
        right.pack(side='right')
        widgets.icon_button(right, self.theme, widgets.PLUS, self._add_port).pack(side='left', padx=(0, 8))
        widgets.icon_button(right, self.theme, widgets.GEAR, self._open_settings).pack(side='left')

    def _build_body(self):
        c = self.theme.colors
        self._body = tk.Frame(self.root, bg=c.panel)
        self._body.pack(fill='both', expand=True)

        # sidebar (master). Detail is hidden by default, so the sidebar fills.
        self._sidebar = tk.Frame(self._body, bg=c.sidebar, width=340)
        self._sidebar.pack(side='left', fill='both' if not self._detail_visible else 'y',
                           expand=not self._detail_visible)
        self._sidebar.pack_propagate(False)
        self._body_divider = tk.Frame(self._body, bg=c.border_soft, width=1)
        if self._detail_visible:
            self._body_divider.pack(side='left', fill='y')

        # Start all / Stop all toolbar at the top of the list
        toolbar = tk.Frame(self._sidebar, bg=c.sidebar)
        toolbar.pack(side='top', fill='x', padx=14, pady=(14, 2))
        widgets.primary_button(toolbar, self.theme, 'Start all', self._start_all,
                               glyph=widgets.TRIANGLE).pack(side='left', padx=(0, 8))
        widgets.FlatButton(toolbar, self.theme, 'Stop all', self._stop_all,
                           glyph=widgets.SQUARE, bg=c.chip_muted_bg, fg=c.text_medium2,
                           border=c.border).pack(side='left')

        scroll_host = tk.Frame(self._sidebar, bg=c.sidebar)
        scroll_host.pack(side='top', fill='both', expand=True)
        self._list_inner = self._make_scrollable(scroll_host)
        self._add_footer = tk.Label(
            self._list_inner, text=widgets.PLUS + '  Add serial → TCP port',
            bg=c.sidebar, fg=c.text_muted, font=self.theme.ui(12, 600),
            highlightthickness=1, highlightbackground=c.dash, highlightcolor=c.dash,
            pady=12, cursor='hand2')
        self._add_footer.pack(fill='x', pady=(4, 4))
        self._add_footer.bind('<Button-1>', lambda _e: self._add_port())
        self._bind_sidebar_wheel(self._add_footer)

        # detail
        self.detail = DetailPanel(self._body, self.theme, {
            'start': self._start_one,
            'stop': self._stop_one,
            'edit': self._edit_port,
            'remove': self._remove_port,
            'save': self._save,
        })
        self._detail_pack = dict(side='left', fill='both', expand=True, padx=20, pady=18)
        if self._detail_visible:
            self.detail.pack(**self._detail_pack)

    def _make_scrollable(self, parent):
        c = self.theme.colors
        canvas = tk.Canvas(parent, bg=c.sidebar, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(parent, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True, padx=(14, 0), pady=14)

        inner = tk.Frame(canvas, bg=c.sidebar)
        window = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>',
                   lambda _e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',
                    lambda e: canvas.itemconfigure(window, width=e.width - 14))

        def on_wheel(event):
            delta = 1 if getattr(event, 'num', None) == 5 or event.delta < 0 else -1
            canvas.yview_scroll(delta, 'units')
            return 'break'

        # Bind the wheel only to sidebar widgets (not bind_all) so scrolling the
        # console does not move the port list. Cards/footer are bound as added.
        def bind_wheel(widget):
            for seq in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
                widget.bind(seq, on_wheel)
            for child in widget.winfo_children():
                bind_wheel(child)
        self._bind_sidebar_wheel = bind_wheel
        bind_wheel(canvas)
        return inner

    # ------------------------------------------------------------ services
    def _load(self):
        for cfg in config_mod.load_configs(self.config_path):
            self._add_service(cfg, select=False)
        errors = []
        for service in self.services:
            if service.config.autostart:
                ok, err = self._try_start(service)
                if not ok:
                    errors.append(err)
        if self.services:
            # Pre-select the first port (highlighted) but keep the panel hidden.
            self.selected = self.services[0]
            self.detail.show(self.services[0])
            self._update_cards_state()
        else:
            self.detail.show(None)
        self._refresh()
        if errors:
            messagebox.showwarning('Autostart',
                                   'Some ports could not start:\n\n' + '\n'.join(errors))

    def _add_service(self, cfg, select=True):
        service = PortService(cfg, on_event=self._on_event)
        self.services.append(service)
        card = PortCard(self._list_inner, self.theme, service, self._select, self._chevron)
        card.pack(fill='x', pady=(0, 10), before=self._add_footer)
        self._bind_sidebar_wheel(card)
        self.cards.append(card)
        if select:
            self._select(service)
        return service

    def _card_for(self, service):
        for card in self.cards:
            if card.service is service:
                return card
        return None

    def _select(self, service):
        self.selected = service
        if not self._detail_visible:
            self._show_detail()
        self._update_cards_state()
        self.detail.show(service)

    def _update_cards_state(self):
        for card in self.cards:
            card.set_state(card.service is self.selected, self._detail_visible)

    def _chevron(self, service):
        """Card chevron: hide the panel if it's the open one, else select+show."""
        if service is self.selected and self._detail_visible:
            self._hide_detail()
        else:
            self.selected = service
            self._show_detail()
            self._update_cards_state()
            self.detail.show(service)

    def _show_detail(self):
        if self._detail_visible:
            return
        self._detail_visible = True
        self._sidebar.pack_configure(fill='y', expand=False)
        self._body_divider.pack(side='left', fill='y', after=self._sidebar)
        self.detail.pack(**self._detail_pack)
        self.root.minsize(820, 560)
        self.root.geometry('{}x{}'.format(self._expanded_width, self.root.winfo_height()))
        self._update_cards_state()

    def _hide_detail(self):
        if not self._detail_visible:
            return
        width = self.root.winfo_width()
        if width > 100:
            self._expanded_width = width
        self._detail_visible = False
        self.detail.pack_forget()
        self._body_divider.pack_forget()
        self._sidebar.pack_configure(fill='both', expand=True)
        # Shrink to a compact list; lower the minimum so the window can narrow.
        self.root.minsize(330, 400)
        self.root.geometry('{}x{}'.format(_COLLAPSED_WIDTH, self.root.winfo_height()))
        self._update_cards_state()

    # ----------------------------------------------------------- actions
    def _try_start(self, service):
        try:
            service.start()
            return True, None
        except Exception as exc:
            return False, '{} → :{}: {}'.format(
                service.config.label, service.config.tcp_port, exc)

    def _start_one(self, service):
        ok, err = self._try_start(service)
        if not ok:
            messagebox.showerror('Start failed', err)
        self._refresh()

    def _stop_one(self, service):
        service.stop()
        self._refresh()

    def _start_all(self):
        errors = []
        for service in self.services:
            ok, err = self._try_start(service)
            if not ok:
                errors.append(err)
        if errors:
            messagebox.showerror('Start all', 'Some ports could not start:\n\n' + '\n'.join(errors))
        self._refresh()

    def _stop_all(self):
        for service in self.services:
            service.stop()
        self._refresh()

    def _add_port(self):
        cfg = open_dialog(self.root, self.theme, [s.config for s in self.services])
        if cfg is None:
            return
        self._add_service(cfg, select=True)
        self._save()
        self._refresh()

    def _edit_port(self, service):
        others = [s.config for s in self.services]
        cfg = open_dialog(self.root, self.theme, others, config=service.config)
        if cfg is None:
            return
        was_running = service.running
        if was_running:
            service.stop()
        service.config = cfg
        if was_running:
            self._try_start(service)
        card = self._card_for(service)
        if card:
            card.destroy()
            self.cards.remove(card)
            new_card = PortCard(self._list_inner, self.theme, service, self._select, self._chevron)
            new_card.pack(fill='x', pady=(0, 10), before=self._add_footer)
            self._bind_sidebar_wheel(new_card)
            self.cards.append(new_card)
        self._select(service)
        self._save()
        self._refresh()

    def _remove_port(self, service):
        if not messagebox.askyesno(
                'Remove', 'Remove mapping {} → :{}?'.format(
                    service.config.label, service.config.tcp_port)):
            return
        if service.running:
            service.stop()
        card = self._card_for(service)
        if card:
            card.destroy()
            self.cards.remove(card)
        self.services.remove(service)
        if self.selected is service:
            self.selected = None
            if self.services:
                self._select(self.services[0])
            else:
                self.detail.show(None)
        self._save()
        self._refresh()

    def _open_settings(self):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label='Save configuration', command=self._save)
        menu.add_command(label='Reload configuration', command=self._reload)
        menu.add_separator()
        menu.add_command(label='Config: {}'.format(self.config_path), state='disabled')
        try:
            x = self.root.winfo_pointerx()
            y = self.root.winfo_pointery()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _reload(self):
        if not messagebox.askyesno('Reload', 'Stop all ports and reload config from disk?'):
            return
        self._stop_all()
        for card in self.cards:
            card.destroy()
        self.cards = []
        self.services = []
        self.selected = None
        self._load()

    # -------------------------------------------------------------- events
    def _on_event(self, service, event):
        # Called from backend threads: just hand off to the main loop.
        self.events.put((service, event))

    def _tick(self):
        try:
            while True:
                service, event = self.events.get_nowait()
                self.detail.append_log(service, event)
        except queue.Empty:
            pass

        self._tick_count += 1
        if self._tick_count % _REFRESH_EVERY == 0:
            for service in self.services:
                service.poll()
            self._refresh()

        self.root.after(_TICK_MS, self._tick)

    def _refresh(self):
        clients = 0
        for card in self.cards:
            card.refresh()
            clients += card.service.client_count
        self.detail.refresh()
        n = len(self.services)
        self._summary.configure(text='{} mapping{} · {} client{}'.format(
            n, '' if n == 1 else 's', clients, '' if clients == 1 else 's'))

    # --------------------------------------------------------------- close
    def _save(self):
        try:
            config_mod.save_configs(self.config_path, [s.config for s in self.services])
        except OSError as exc:
            messagebox.showerror('Save failed', 'Could not write {}:\n{}'.format(
                self.config_path, exc))

    def _on_close(self):
        for service in self.services:
            service.stop()
        self._save()
        self.root.destroy()


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(
        prog='python -m serialtcp.gui',
        description='Tkinter Port Manager for serial -> TCP mappings.')
    parser.add_argument('config', nargs='?', default=config_mod.default_config_path(),
                        help='YAML config file (default: ./%s)' % config_mod.DEFAULT_CONFIG_NAME)
    args = parser.parse_args(argv)
    App(args.config).run()


if __name__ == '__main__':
    main()
