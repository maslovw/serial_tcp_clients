"""Load and save the YAML list of serial -> TCP port mappings.

Config shape::

    ports:
      - device: COM3
        tcp_port: 5000
        baudrate: 115200
        parity: N
        autostart: true
      - device: /dev/ttyUSB0
        tcp_port: 5002
"""

import os
import yaml

from serialtcp.service import PortConfig

DEFAULT_CONFIG_NAME = 'serialtcp_ports.yaml'


def default_config_path():
    return os.path.join(os.getcwd(), DEFAULT_CONFIG_NAME)


def load_configs(path):
    """Return a list of PortConfig from ``path`` (empty list if missing)."""
    if not path or not os.path.exists(path):
        return []
    with open(path, 'r') as fh:
        data = yaml.safe_load(fh)
    if not data:
        return []
    if isinstance(data, dict):
        ports = data.get('ports', [])
    elif isinstance(data, list):
        ports = data
    else:
        ports = []
    configs = []
    for entry in ports:
        if isinstance(entry, dict) and entry.get('device') and entry.get('tcp_port'):
            configs.append(PortConfig.from_dict(entry))
    return configs


def save_configs(path, configs):
    """Write the mappings back to ``path`` as YAML."""
    data = {'ports': [c.to_dict() for c in configs]}
    with open(path, 'w') as fh:
        yaml.safe_dump(data, fh, sort_keys=False, default_flow_style=False)
