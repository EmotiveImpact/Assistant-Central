# Experimental offline MCP bridge r3

A tools-only real MCP SDK adapter to frozen r2, with bounded already-decoded
in-memory input and no host authentication. This separate experimental release
preserves every r2 file. See DESIGN.md for exact limits and exclusions.

From this directory, using the already available Python 3.12.14 environment:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python run_all_checks.py
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python run_bridge_checks.py
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python run_demo.py
```

The combined command checks the r3 source freeze and all inherited r2 files, runs
the original r2 aggregate unchanged, then runs the implementation and independent
bridge checks and the full SDK request/result demo. Final counts and fresh-archive
results are recorded in verification-r3.json and evidence/. MCP_SOURCE_MANIFEST.json
is the full source freeze; BASELINE_R2_FILES.json preserves all 65 inherited files.

The demo uses two recipient-owned endpoint processes and four separate stores.
Each assistant only proposes exact text or reads its own local state. Every receive
grant, review, approval/release, processing and publication remains a separate
explicit synthetic-owner step. It is not two real authenticated human owners.
Returning a proposal is never permission to send it. Lost results remain uncertain.

Independent review is included in INDEPENDENT_REVIEW.md. Error redaction applies
to protocol/tool responses, not a verified logging-isolation boundary. SDK debug
logging can include forwarded tool data; a future embedding must set and review
its logging policy. The bridge cannot control a host's unrelated tools.

The complete original r2 lives unchanged inside baseline_r2. Its original recursive
freeze verifier and aggregate remain runnable from inside that directory:

```sh
cd baseline_r2
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python run_facade_checks.py
```

Legacy negotiation checks end at 2025-11-25; the SDK ClientSession roundtrip uses
2025-11-25. This is not a full conformance certification, MCP 2026 acceptance,
stdio/HTTP integration or native host compatibility. A future raw transport must
bound bytes before decoding and preserve the same narrow owner boundary. No host
installation, real identity enrollment, credential setup or live connection was
performed. The additional
concurrent-shutdown/descriptor-lifecycle review remains uncompleted; excluded
from this scope.
