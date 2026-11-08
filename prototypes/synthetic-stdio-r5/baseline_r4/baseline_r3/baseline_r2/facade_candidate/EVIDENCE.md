# Candidate evidence

November 8, 2026. Offline application-layer implementation only.

- Focused candidate suite: **25 tests passed**, including 24 local/unit tests and
  one normal sequential two-process facade roundtrip. See
  `facade_evidence/focused.txt`.
- Unchanged r1 aggregate: **55 tests passed** plus original synthetic demo; all
  **20 frozen manifest files verified**. See `facade_evidence/r1-regression.txt`.
  This reruns existing regression coverage; it is not a new audit of excluded
  concurrency/shutdown/descriptor-lifecycle behavior.
- Separate candidate demo passed: `facade_evidence/demo.json`. The demo explicitly
  checks both endpoint snapshots are unchanged by proposal submission, then runs
  synthetic owner approval/release, recipient processing, separate result proposal,
  its exact owner approval/release and trusted processed-only publication.
- **39 copied baseline files remain byte-identical** to the frozen r1 directory,
  including protocol.py, endpoint.py, fixture.py, pipes.py and worker.py. The five
  runtime hashes and file comparison are in `facade_evidence/baseline-delta.json`.
  Original r1, v29, archives and APEX directories were not edited.

New candidate files are `facade_candidate/{__init__.py,store.py,demo.py,DESIGN.md,
EVIDENCE.md}`, `facade_tests/test_facade.py` and candidate evidence files.
No existing file was modified. The r1 aggregate intentionally does not enumerate
new candidate files; it remains evidence for the preserved baseline, not candidate
manifest coverage. No candidate archive or frozen release was produced.

Coverage includes the exact three-method surface and extra-field rejection;
Unicode scalar/1024-byte boundary; exact content identity/no normalization;
declined and unknown history after reopen; cross-actor status separation;
immutable task/actor/both-incarnation binding; finite history; detached values;
review/content/grant digests; invalid signed grant; known rejection vs generic
exception; actual response correlation, public packet/header shape and fixed binding checks;
local-store connection closure on constructor binding failure; allowlists; malformed response stays
unknown; snapshot absence/cancel cannot resolve uncertainty; committed content is
not release; wrong snapshot actor/incarnation; no raw inbox exposure; unpublished
vs published-empty; monotonic retained processed history and publication revision.

The initial focused run had one **test assertion error**: SQLite Connection
objects are callable, so checking that no stored object was callable incorrectly
failed. The assertion now checks the precise allowed local store fields instead.
The failed initial output is retained in `facade_evidence/initial-focused.txt`.
No runtime authority workaround or excluded-area investigation was involved.

Limits: proposal stores persist while endpoint identities do not survive r1 exit.
Snapshot task/peer provenance, actual command execution and actual response origin
are trusted-composition responsibilities. Snapshot committed-content observation
cannot prove operation causation or packet export. The model tool surface is not
OS/IPC isolation. No live/native-host compatibility or production-readiness claim.

Application-review correction: successful-response recording now rejects malformed,
wrong-direction and wrong-incarnation packet headers before changing unknown.
Construction failure closes its local SQLite connection. Text length is rejected
before UTF-8 encoding when already above 1024 characters, then the exact byte
bound is enforced; this is not a transport/host allocation limit claim. The pre-correction
23-test passing log is retained as `facade_evidence/focused-before-corrections.txt`.
These changes concern only new application modules, not endpoint transport.

`committed_content_observed` is terminal in r2: later actual response/rejection
recording cannot enrich it. This conservative evidence-retention limitation keeps
underlying operation/export/delivery uncertainty explicit, without a retry permit.
