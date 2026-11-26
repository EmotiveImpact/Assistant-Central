"""Verify frozen source hashes, run targeted tests, then run the fictional demo."""
import hashlib
import json
from pathlib import Path
import platform
import sys
import unittest

import cryptography

ROOT = Path(__file__).resolve().parent


def main():
    manifest = json.loads((ROOT / 'SOURCE_MANIFEST.json').read_text())
    for name, expected in manifest['files'].items():
        path = ROOT / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit('Source integrity check failed: ' + name)
    source = {str(p.relative_to(ROOT)) for pattern in ('independent_peer/*.py', 'tests/*.py', 'docs/*.md') for p in ROOT.glob(pattern)}
    source.update(('README.md', 'requirements-experiment.txt', 'run_checks.py'))
    if source != set(manifest['files']):
        raise SystemExit('Source allowlist does not match manifest')
    print('SYNTHETIC OFFLINE EXPERIMENT CHECKS', flush=True)
    print('Python:', platform.python_version(), 'cryptography:', cryptography.__version__, flush=True)
    print('Source hashes verified:', len(source), flush=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    from independent_peer.demo import run
    print(json.dumps(run(), indent=2), flush=True)
    print('Aggregate checks passed. Experimental only; see docs/DESIGN.md for limits.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
