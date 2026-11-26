"""Run the preserved A4A sanitization checks without installing its full SDK."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from vendor.a4a import sanitize


class UpstreamTests(unittest.TestCase):
    def test_original_sanitization_checks(self):
        source = Path(__file__).parent.parent / "vendor/a4a/test_sanitize_original.py"
        package = types.ModuleType("a4a")
        package.sanitize = sanitize
        previous = {name: sys.modules.get(name) for name in ("a4a", "a4a.sanitize")}
        try:
            sys.modules["a4a"] = package
            sys.modules["a4a.sanitize"] = sanitize
            spec = importlib.util.spec_from_file_location("upstream_tests", source)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            tests = [v for name, v in vars(module).items() if name.startswith("test_") and callable(v)]
            self.assertEqual(len(tests), 11)
            for test in tests:
                with self.subTest(name=test.__name__):
                    test()
        finally:
            for name, value in previous.items():
                if value is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = value
