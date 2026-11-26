"""Trusted local composition; baseline is a fixed sibling, not a host install."""
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'baseline_r2'))
if __name__=='__main__':
    suite=unittest.defaultTestLoader.discover(str(ROOT/'bridge_tests'))
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
