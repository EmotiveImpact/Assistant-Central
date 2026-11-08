"""Use the same trusted team module identity as its CLI and protocol binding."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "team"))

from team_workflow import (AgentRef, TaskSpec, TeamPlan, TeamWorkflow, Denied,
                           bounded_text, canonical, digest, identifier)

# Exact-class checks must work across both local composition lanes. Refuse an
# already imported module from somewhere else; this is not an interpreter sandbox.
if Path(sys.modules["team_workflow"].__file__).resolve() != ROOT / "team" / "team_workflow.py":
    raise RuntimeError("Unexpected execution team module origin")
