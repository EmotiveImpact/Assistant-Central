#!/usr/bin/env python3
"""Run only the r5 builder and independent stdio checks, never peer suites."""
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
root = Path(__file__).resolve().parent
for label, relative in (
    ('20 targeted launcher checks', 'run_checks.py'),
    ('19 independent stdio checks', 'independent_tests/run_checks.py'),
):
    print(label, flush=True)
    result = subprocess.run([sys.executable, '-I', '-B', str(root / relative)], cwd=root)
    if result.returncode:
        raise SystemExit(result.returncode)
print('All 39 r5 checks passed. Native hosts and inherited peer suites were not run.', flush=True)
