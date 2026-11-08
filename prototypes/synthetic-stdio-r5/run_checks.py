#!/usr/bin/env python3
"""Targeted synthetic launcher checks only; never executes inherited runners."""
from pathlib import Path
import sys
import unittest
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern='test_launcher.py')
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
