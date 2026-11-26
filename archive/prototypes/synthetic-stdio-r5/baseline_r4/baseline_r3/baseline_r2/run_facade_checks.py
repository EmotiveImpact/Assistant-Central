"""Verify both freezes, rerun existing regressions, and check the additive facade."""
import hashlib
import json
from pathlib import Path
import platform
import sys
import unittest

import cryptography

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    manifest = json.loads((ROOT / 'FACADE_SOURCE_MANIFEST.json').read_text())
    expected = manifest['files']
    actual = {
        p.relative_to(ROOT).as_posix()
        for p in ROOT.rglob('*')
        if p.is_file() and '__pycache__' not in p.parts
        and (p.suffix in ('.py', '.md') or p.name in ('requirements-experiment.txt', 'SOURCE_MANIFEST.json'))
    }
    if actual != set(expected):
        raise SystemExit('Full candidate source allowlist does not match manifest')
    for name, value in expected.items():
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or sha(path) != value:
            raise SystemExit('Candidate source integrity check failed: ' + name)
    baseline = json.loads((ROOT / 'SOURCE_MANIFEST.json').read_text())['files']
    for name, value in baseline.items():
        if sha(ROOT / name) != value:
            raise SystemExit('Preserved r1 source differs: ' + name)
    return len(expected), len(baseline)


def main():
    full, old = verify()
    print('EXPERIMENTAL R2: OFFLINE LOCAL PROPOSAL FACADE', flush=True)
    print('Python:', platform.python_version(), 'cryptography:', cryptography.__version__, flush=True)
    print('Candidate source hashes:', full, '; preserved r1 source hashes:', old, flush=True)
    loader = unittest.TestLoader()
    suite = unittest.TestSuite([
        loader.discover(str(ROOT / 'tests'), top_level_dir=str(ROOT)),
        loader.discover(str(ROOT / 'facade_tests'), top_level_dir=str(ROOT)),
    ])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    from independent_peer.demo import run as baseline_demo
    from facade_candidate.demo import run as facade_demo
    print(json.dumps({'preserved_r1_demo': baseline_demo(), 'facade_demo': facade_demo()}, indent=2), flush=True)
    print('Reruns existing regressions and new sequential application checks only.', flush=True)
    print('Additional concurrent-shutdown/descriptor-lifecycle review remains uncompleted.', flush=True)
    print('No native host, real identity, live transport, or production acceptance.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
