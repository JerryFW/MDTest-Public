#!/usr/bin/env python3
"""Backward-compatible launcher for the packaged MDTest application.

Existing commands such as ``python MDTest.py auto-safe ...`` remain valid.
The implementation now lives in the installable ``mdtest`` package under
``src/`` so scripts, notebooks, and the CLI use the same computational engine.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Preserve direct execution from a source checkout before installation.
_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from mdtest.cli import entrypoint

if __name__ == "__main__":
    entrypoint()
