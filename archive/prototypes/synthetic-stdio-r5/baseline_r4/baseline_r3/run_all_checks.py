"""Verify additive r3 and preserved r2, then run their distinct offline suites."""
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent
BASELINE = ROOT / 'baseline_r2'
sys.path.insert(0, str(BASELINE))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_file(path):
    return path.suffix in ('.py', '.md') or path.name.startswith('requirements') and path.suffix == '.txt' or path.name in (
        'SOURCE_MANIFEST.json', 'FACADE_SOURCE_MANIFEST.json', 'BASELINE_R2_FILES.json')


def verify():
    expected = json.loads((ROOT / 'MCP_SOURCE_MANIFEST.json').read_text())['files']
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and source_file(p)}
    if actual != set(expected):
        raise SystemExit('R3 source allowlist differs from freeze')
    for name, value in expected.items():
        path = ROOT / name
        if path.is_symlink() or not path.is_file() or sha(path) != value:
            raise SystemExit('R3 source integrity check failed: ' + name)
    old = json.loads((ROOT / 'BASELINE_R2_FILES.json').read_text())['files']
    old_actual = {p.relative_to(BASELINE).as_posix() for p in BASELINE.rglob('*')
                  if p.is_file() and '__pycache__' not in p.parts}
    if old_actual != set(old):
        raise SystemExit('Preserved r2 file allowlist differs')
    for name, value in old.items():
        path = BASELINE / name
        if path.is_symlink() or sha(path) != value:
            raise SystemExit('Preserved r2 file differs: ' + name)
    return len(expected), len(old)


def main():
    full, baseline = verify()
    print('EXPERIMENTAL R3: OFFLINE MCP TOOLS BRIDGE', flush=True)
    print('Source hashes:', full, '; preserved r2 files:', baseline, flush=True)
    print('Python:', platform.python_version(), flush=True)
    print('Dependencies:', json.dumps({n: version(n) for n in ('mcp', 'anyio', 'pydantic', 'cryptography')}), flush=True)
    # Rerun the original verifier unchanged, in its own original directory scope.
    subprocess.run([sys.executable, 'run_facade_checks.py'], cwd=BASELINE, check=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'bridge_tests'), top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        return 1
    import anyio
    from run_demo import run
    print(json.dumps(anyio.run(run), indent=2), flush=True)
    print('Preserved r2: 91 tests. Additional bridge tests:', result.testsRun, flush=True)
    print('Combined tests:', 91 + result.testsRun, '; bridge skips:', len(result.skipped), flush=True)
    print('SDK interoperability evidence only; no native host, raw-byte transport or live network acceptance.', flush=True)
    print('Additional concurrent-shutdown/descriptor-lifecycle review remains uncompleted.', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
