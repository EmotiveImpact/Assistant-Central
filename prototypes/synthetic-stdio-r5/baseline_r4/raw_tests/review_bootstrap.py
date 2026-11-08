"""Run from this review directory or after copying into candidate/raw_tests."""
import os
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
# Prefer this copied archive's own code; an external override must not redirect it.
choices = [HERE.parent] + ([Path(os.environ['RAW_R4_ROOT'])] if 'RAW_R4_ROOT' in os.environ else []) + [HERE.parent / 'agent-network-independent-peer-raw-r4']
ROOT = next((p for p in choices if (p / 'raw_bridge/transport.py').is_file()), None)
if ROOT is None:
    raise RuntimeError('Set RAW_R4_ROOT to the candidate directory.')
for p in (ROOT / 'baseline_r3/baseline_r2', ROOT / 'baseline_r3', ROOT):
    sys.path.insert(0, str(p))
