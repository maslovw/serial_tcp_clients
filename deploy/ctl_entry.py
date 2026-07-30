"""PyInstaller entry point for serial-tcp-ctl.exe.

Mirrors ``gui/serialtcp_gui/__main__.py``: the packaged script is executed as
``__main__``, so it must import the CLI through the package (a relative import
inside ``cli.py`` has no parent package when the module *is* the entry script).
"""
import sys

from serialtcp_gui.cli import main

sys.exit(main())
