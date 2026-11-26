# Experimental r2: a local assistant proposal facade

November 8, 2026. Entirely offline and synthetic. This is a separate additive
experiment, not a replacement for stable v29 or independent-peer r1.

The new layer gives each local assistant three methods: propose exact text,
inspect its own proposal status, and read its owner's last published processed
inbox. Proposals are unsigned. They cannot grant permission, send, process incoming
messages, configure peers, or access an owner-control pipe.

The sequential demo uses two independently running endpoints and four separate
SQLite stores: two recipient-owned endpoint stores and two local proposal stores.
Explicit synthetic-owner decisions remain necessary for approval/release, receive
grants and processing. Proposal submission is checked to leave both endpoint
snapshots unchanged. The two endpoint processes still use the preserved r1 runtime.

## Run

Python 3.12.14 and cryptography 50.0.0 were already available in the test environment.
No dependency or host installation was performed. From this directory:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python run_facade_checks.py
PYTHONDONTWRITEBYTECODE=1 python -m facade_candidate.demo
```

The r2 aggregate verifies the full candidate freeze and original r1 source freeze,
then runs **91 tests**: 55 preserved r1 tests, 25 facade implementation tests and
11 independent application-contract tests. Both original and new synthetic demos
also run. The implementation tests include one normal sequential two-process
roundtrip; the independent facade tests use sequential local endpoint objects,
not process transport. See final verification metadata and evidence for actual
run results and platform. Test counts are not production-readiness measures.

Original `README.md`, `run_checks.py`, `SOURCE_MANIFEST.json` and other r1 files are
deliberately unchanged. Their 55-test descriptions refer to that preserved baseline.
Use `run_facade_checks.py` for the combined r2 candidate. The complete r2 source
allowlist and hashes are in `FACADE_SOURCE_MANIFEST.json`.

## Exact meaning and uncertainty

- Each proposal store is bound to the exact task, actor and both public endpoint
  incarnations. Reopening under a changed binding is rejected.
- Exact text is nonempty Unicode scalar text, at most 1,024 UTF-8 bytes. Nothing is
  normalized, truncated or silently converted from v29's different schemas.
- Repeated exact content returns the same durable decision, including declines
  and uncertainty. A full 64-record store does not evict that history.
- Owner preparation commits an unknown outcome before returning the one exact
  approval-and-release command. The facade never executes or retries it.
- A recorded successful response means the trusted owner composition observed
  local approval/release. It does not establish peer receipt or processing.
- A matching outbox snapshot proves only observed committed content. It does not
  establish which operation caused it or whether packet bytes were exported.
  This observation is terminal in r2: even a later actual response/rejection cannot
  enrich it. That is a conservative evidence-retention limitation, not resolution
  of uncertainty or permission to retry.
- Processed-inbox publication is historical local knowledge, not a fresh network
  read. Incoming content is untrusted data, never authority. Cancellation cannot
  erase published processing history or recall already released bytes.

## Reviewed scope and limits

The new application layer was independently reviewed. No blocking authority
defect was found within its documented trusted-composition boundary. The review
and eleven additional tests are included. Parent review also tightened packet
direction/incarnation shape checks, local SQLite cleanup on constructor rejection,
and input length checks before encoding. None changed the original endpoint or
transport code.

This is a logical tool-dispatch boundary, not isolation from arbitrary Python code
or the OS user. One supervisor still simulates both owners; no real human identity
or host authentication is implemented. Actual response origin, exact command
execution and snapshot provenance remain trusted. The frozen endpoint snapshot
does not carry task or peer binding, so fixed composition must supply that context.

The additional concurrent-shutdown/descriptor-lifecycle review remains **not
completed**. This work neither retries that review nor clears its gate. Existing
r1 regression reruns and the new sequential application checks are not substitute
evidence for it. Same-user process isolation, persistent key recovery, live transport,
real relationship enrollment, native MCP/host acceptance, wake delivery, and
production security remain unverified or unimplemented.

No account, credentials, installation, listener, socket, browser action, live
message or publication was involved. Stable v29, original r1, and prior delivered
archives remain unchanged. The new facade does not import v29 or claim A4A/MCP
wire compatibility. Further host integration requires explicit schema mapping,
trusted owner composition and separate acceptance testing.

Details: `facade_candidate/DESIGN.md`, `facade_candidate/INDEPENDENT_REVIEW.md`,
and `facade_evidence/`. Worker-stage evidence records precede the combined freeze;
final aggregate/fresh-archive evidence and verification metadata describe this
packaged r2 source.
