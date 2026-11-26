"""Fixed local composition, not host installation."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'baseline_r3'))
sys.path.insert(0, str(ROOT / 'baseline_r3' / 'baseline_r2'))
