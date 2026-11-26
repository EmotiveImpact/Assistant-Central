"""Verify r4 and the complete preserved r3, then run distinct offline checks."""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys
import unittest

import bootstrap

ROOT = Path(__file__).resolve().parent
BASELINE = ROOT / 'baseline_r3'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_file(path):
    return (path.suffix in ('.py', '.md')
            or path.name.startswith('requirements') and path.suffix == '.txt'
            or path.name in ('SOURCE_MANIFEST.json', 'FACADE_SOURCE_MANIFEST.json',
                            'MCP_SOURCE_MANIFEST.json', 'BASELINE_R2_FILES.json',
                            'BASELINE_R3_FILES.json'))


def verify():
    expected = json.loads((ROOT / 'RAW_SOURCE_MANIFEST.json').read_text())['files']
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and source_file(p)}
    if actual != set(expected):
        raise SystemExit('R4 source allowlist differs from freeze')
    for name, value in expected.items():
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or sha(path) != value:
            raise SystemExit('R4 source integrity check failed: ' + name)
    old = json.loads((ROOT / 'BASELINE_R3_FILES.json').read_text())['files']
    old_actual = {p.relative_to(BASELINE).as_posix() for p in BASELINE.rglob('*')
                  if p.is_file() and '__pycache__' not in p.parts}
    if old_actual != set(old):
        raise SystemExit('Preserved r3 file allowlist differs')
    for name, value in old.items():
        path = BASELINE / name
        if path.is_symlink() or sha(path) != value:
            raise SystemExit('Preserved r3 file differs: ' + name)
    return len(expected), len(old)


def main():
    full, baseline = verify()
    print('EXPERIMENTAL R4: OFFLINE UTF-8/LF MCP BYTE BOUNDARY', flush=True)
    print('Source hashes:', full, '; preserved r3 files:', baseline, flush=True)
    print('Python:', platform.python_version(), flush=True)
    print('Dependencies:', json.dumps({n: version(n) for n in ('mcp', 'anyio', 'pydantic', 'cryptography')}), flush=True)
    subprocess.run([sys.executable, 'run_all_checks.py'], cwd=BASELINE, check=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'raw_tests'), top_level_dir=str(ROOT))
    # The portable review bootstrap must not redirect this release run elsewhere.
    from raw_tests import review_bootstrap
    from raw_bridge import codec, transport
    from mcp_bridge import bridge
    from facade_candidate import store
    if review_bootstrap.ROOT.resolve() != ROOT:
        raise SystemExit('Independent checks resolved a different candidate')
    for module in (codec, transport, bridge, store):
        if not Path(module.__file__).resolve().is_relative_to(ROOT):
            raise SystemExit('A checked module was imported outside this archive')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    import anyio
    from run_demo import run
    print(json.dumps(anyio.run(run), indent=2), flush=True)
    print('Preserved r3: 124 tests. Additional raw-boundary tests:', result.testsRun, flush=True)
    print('Combined tests:', 124 + result.testsRun, '; raw-boundary skips:', len(result.skipped), flush=True)
    print('Synthetic byte streams only: no native host, stdio/HTTP connection, real owner enrollment or live network.', flush=True)
    print('Additional peer-process concurrent-shutdown/descriptor-lifecycle review remains uncompleted.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
