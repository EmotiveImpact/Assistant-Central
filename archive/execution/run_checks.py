"""Run execution tests with the same offline guard used by the team fixture."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from team.run_checks import offline_guard

if __name__ == "__main__":
    sys.addaudithook(offline_guard)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "execution" / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun else 1)
