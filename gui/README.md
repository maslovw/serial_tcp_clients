# serial-tcp-clients-gui

Tkinter **Port Manager** desktop GUI for
[`serial-tcp-clients`](https://github.com/maslovw/serial_tcp_clients): manage
many serial -> TCP mappings at once from a single YAML config, with per-port
start/stop, live throughput, a colour-coded console and an integrated terminal.

```bash
pip install serial-tcp-clients-gui
serial-tcp-gui                 # or: python -m serialtcp_gui [config.yaml]
```

This package pulls in `serial-tcp-clients` (the CLI/backend) and PyYAML
automatically. It also needs **Tkinter**, which ships with most CPython builds;
on Linux install it from your package manager (Debian/Ubuntu:
`apt install python3-tk`).

An optional **REST control API** (health, configuration, port states, start/stop)
is available with the `api` extra, served on `http://localhost:410` by default:

```bash
pip install "serial-tcp-clients-gui[api]"
```

The package also installs **`serial-tcp-ctl`**, a stdlib-only command-line client
for that API (`serial-tcp-ctl health`, `ports`, `show`, `config`, `add`, `set`,
`start`, `stop`, `remove`).

See the [main README](https://github.com/maslovw/serial_tcp_clients#gui-port-manager)
for full GUI documentation.
