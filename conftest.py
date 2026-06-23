"""Test bootstrap.

The base package ``serialtcp`` is importable from the repo root; the GUI package
``serialtcp_gui`` lives in the ``gui/`` subproject, so add it to ``sys.path`` for
the suite (avoids needing an editable install of both packages just to run tests).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'gui'))
