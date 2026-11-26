# Trusted fixture pipe deadlines

This helper is a sequential, single-owner Linux fixture launcher, not a general
agent tool, OS sandbox, process-tree supervisor, or production transport.
The fixed-script allowlist, interpreter, argv, environment, working directory,
and close-fds policy remain unchanged.

- Each `read()` has one absolute 10-second startup/frame deadline.
- Each `request()` has one absolute 10-second deadline shared by writing the
  entire request and reading/decoding one response. OS process creation and
  caller-side JSON serialization are outside this transport deadline.
- Raw nonblocking pipes and selectors handle partial writes/reads and EAGAIN.
  No helper thread, retry, restart, or additional subprocess is used.
- Requests remain at most 16,384 encoded bytes including newline. Responses
  remain at most 16,384 or the explicitly selected 65,536 bytes including
  newline. Pending stdout storage never exceeds the response cap plus one byte;
  stderr is discarded in chunks of at most 4,096 bytes, never accumulated or
  included in errors. Each selector event checks the deadline to prevent floods
  or continual partial progress from extending it.
- Frames require newline termination, strict UTF-8 and valid JSON. Duplicate
  object keys, non-finite constants and float overflow are rejected.
- Transport/framing/decode errors close all three pipes, kill the owned child
  if live, and wait for it. Explicit `close()` also kills instead of waiting for
  graceful fixture exit, and can be called repeatedly. Reaping has a separate
  five-second bound; failure to reap is reported, never silently called success.
- Errors are fixed and conservative: the command outcome may be unknown, and
  automatic resending is forbidden. Killing the child cannot roll back a command
  that committed before a lost response. There is no descendant-containment
  promise or untested portability claim.

Tests use explicitly patched controlled Python children, not a production
launcher extension. `tests/test_fixture_ipc_deadlines.py` exercises partial and
unterminated frames, incomplete/invalid UTF-8, byte bounds, stderr saturation,
partial and blocked writes, EAGAIN, shared write/read deadlines, unknown outcome
after a real file side effect, exited/killed children, broken streams, and
idempotent cleanup with Linux descriptor/thread/reaping checks. Existing framing
regressions now use actual binary pipes rather than StringIO/select mocks.


Independent tests add exact byte caps, continuous drip under a fixed deadline,
real pipe backpressure, early output during blocked writes, multiple requests,
preflight failures and reported reap failure. Two workspace integration cases
confirm that a stalled child releases its held workspace lock after failure
before a group stop commits, and startup failure cleans the owned child while
retaining the occupied uncertain task slot. Neither proves immediate stop or
undoes a command that already committed.

See verification-v23.json and its final extracted-source verifier report.

## Optional continuity signer

v25 adds one fixed `continuity_fixture_process.py` entry to the three existing
trusted fixture scripts. It is launched only on a separately confirmed enrollment
in a continuity-enabled workspace, uses the same IPC limits, and signs only the
informational continuity domain. No arbitrary script path or executable selection
is exposed. See CONTINUITY_PROOFS.md for the separate possession-proof boundary.
