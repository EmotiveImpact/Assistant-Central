#!/usr/bin/env python3
"""Load only the colocated independent tests, never inherited release suites."""
import importlib.util
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
path = Path(__file__).resolve().with_name('test_independent.py')
spec = importlib.util.spec_from_file_location('r5_independent_review_tests', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
raise SystemExit(0 if result.wasSuccessful() else 1)
