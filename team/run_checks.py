"""Standard-library-only tests under an audit guard against external activity."""
from pathlib import Path
import sys
import unittest


def offline_guard(event, args):
    if event.startswith("socket.") or event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn"):
        raise RuntimeError("Offline fixture prohibits network and process execution")


if __name__ == "__main__":
    sys.addaudithook(offline_guard)
    root = Path(__file__).resolve().parent
    suite = unittest.defaultTestLoader.discover(str(root / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun else 1)
