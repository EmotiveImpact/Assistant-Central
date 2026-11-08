"""Load the repository's verified r5 building blocks in trusted local composition.

This is not a plugin loader, sandbox, authentication step, or live host setup.
"""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
R5 = ROOT / 'prototypes' / 'synthetic-stdio-r5'
sys.dont_write_bytecode = True


def _load_launcher():
    path = R5 / 'launcher.py'
    spec = importlib.util.spec_from_file_location('assistant_central_frozen_r5_launcher', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Hash validation is useful only with a trusted, nonconcurrently modified checkout.
launcher = _load_launcher()
baseline, PUBLIC_FIXTURE, VERIFIED_R5_INPUTS = launcher.verify_inputs(R5)
for path in (ROOT / 'team', baseline, baseline / 'baseline_r3', baseline / 'baseline_r3' / 'baseline_r2'):
    sys.path.insert(0, str(path))

from team_workflow import TeamWorkflow, Denied, digest, canonical  # noqa: E402
from facade_candidate import AssistantFacade, ProposalStore  # noqa: E402
from independent_peer.protocol import digest as protocol_digest  # noqa: E402

# Refuse an already-imported, differently located same-name package. This does not
# defend against arbitrary Python code with access to this process or its files.
for name, expected in (
    ('team_workflow', ROOT / 'team' / 'team_workflow.py'),
    ('facade_candidate', baseline / 'baseline_r3' / 'baseline_r2' / 'facade_candidate' / '__init__.py'),
    ('independent_peer.protocol', baseline / 'baseline_r3' / 'baseline_r2' / 'independent_peer' / 'protocol.py'),
):
    if Path(sys.modules[name].__file__).resolve() != expected.resolve():
        raise RuntimeError('Unexpected integration module origin')
