# Offline mixed-language scripted peers (v27)

This optional offline fixture adds independent JavaScript encoding/decoding and
lifecycle evidence to the existing fixed Python peer. It is **not native provider
interoperability**, installed-host acceptance, a network roundtrip, human consent,
identity authentication, persistent continuity, automatic wake, or an OS sandbox.

## Run

Use the existing pinned Python dependencies and a trusted installed Node **18 or
newer**. This checkpoint was exercised on Node **v24.22.1**, Linux. Older supported
Node versions have not been separately exercised. Anonymous descriptor passing and
pipe selection are POSIX-oriented; no macOS or Windows runtime acceptance is claimed. Nothing is installed by the demo.

```
python offline_peer_demo.py --mixed-node alice
python offline_peer_demo.py --mixed-node bob
python offline_peer_demo.py --simulate --mixed-node alice
python offline_peer_demo.py --simulate --mixed-node bob
```

Without `--mixed-node`, both children remain Python and no Node discovery occurs.
`--simulate` is still an explicit request for synthetic owner decisions, not human
approval evidence. With no `--simulate`, follow OFFLINE_PEER_DEMO.md's unchanged
console instructions: preview/create/select the exact task, review both bindings,
then `peers-start`, discovery and proposals. Pair, import, review, approve, submit,
send and process remain separate owner actions. Client selection is a closed,
trusted launcher option, not an agent-visible tool or configurable executable.
The chosen actor runs Node; the other actor runs the original Python script.

## Runtime and process boundary

The supervisor resolves `node` from the trusted operator's runtime PATH, excluding
empty/relative entries and the checkpoint directory and its descendants. It
resolves symlinks to a regular executable, rejects world-writable path ancestors,
and checks the major version before launching. Runtime PATH and executable
installation are trusted inputs, not a defense against malicious same-user code.
The version probe uses an empty environment, no input, captured output and discarded
stderr, so it does not contribute protocol messages. No downloads, fallback
substitutions or arbitrary peer commands are accepted.

Mixed demo preflight checks Node before creating sessions or launching either
child. Each Node launch checks again; if the runtime disappears after preflight,
all already-started children are closed and reaped using existing cleanup. A
partially started demo cannot replace/reconnect a peer. A missing runtime before
launch leaves no partially started children. No owner binding or pairing occurs
as a side effect. The full checkpoint verifier requires Node for Python mixed-peer
tests as well as DOM-model checks and reports incomplete if it is absent; the
Python-only application path itself remains usable without Node.

Both fixed children run with an empty environment. In particular, `NODE_OPTIONS`
and `NODE_PATH` are not inherited. Only their ordinary standard streams and two
explicit anonymous descriptors are inherited. The separate fixture signer/executor
allowlist in `fixture_ipc.py` is unchanged. The fixed `.cjs` suffix selects CommonJS even when extracted beneath a parent
Node project configured with `type: module`. The JavaScript client imports only the
built-in `node:fs`; it has no SDK, plugin interface, sockets, data evaluation,
provider configuration, owner tools or persistence.

## Wire evidence and limits

The Node script independently implements initialize, version negotiation,
initialized notification, discovery and the three tools (`propose`,
`proposal_status`, `inbox`). Both client implementations verify the returned
protocol version and correlate response IDs before continuing. Node requires
JSON-RPC 2.0 and exactly one of result/error. The server remains responsible for
closed schemas, duplicate-key rejection, actor/task scope, authorization and
request-relative bounds. No server authority or schema checks are relaxed.

Node uses Buffer byte lengths and fatal UTF-8 decoding, not JavaScript UTF-16
string lengths, for framing. Escaped newlines and non-BMP characters are inert
payload data. Node protocol output is capped at 16 KiB excluding LF; input at
32 KiB excluding LF. Control/report frames are capped at 64 KiB including LF.
The supervisor retains its three-second explicit-step pipe deadline, eight-frame
budget, bounded reads/short writes, correlated reports and EOF/timeout cleanup.
These are pipe-wait bounds, not whole-action, spawn or trusted callback deadlines.
No background polling, retry, replacement, callback replay or reconnect is added.

Receipt alone still yields an empty processed inbox. Only the separate owner
`process` action makes an exact request/result visible. `simulate()` now checks the
complete expected envelope, not only the message count. Lost replies after a
committed proposal remain uncertain: inspect existing history; never infer
nondelivery or authorization to resend. Declined history and group stops preserve
the existing fences. Root `.js` and `.cjs` JavaScript source is now included in the checkpoint
source-freeze scope, and root JS symlinks are rejected. Hashes prove local
consistency, not authenticity.

## Tests

`tests/test_mixed_peer_demo.py` exercises both mixed role assignments, exact
Unicode/newline envelopes, receipt-only empty inboxes, early result refusal,
wrong actor/task and owner commands, declined history and stopped groups. Existing
supervisor fault cases run against Node too: EOF, oversize, report mismatch,
timeout, cleanup errors and post-callback response loss without replay. Additional
cases cover byte-exact protocol limits, incompatible negotiation and response IDs,
missing/late runtime failures, clean environment, closed client selection and JS
freeze/symlink handling. Independent review lives in
`tests/test_mixed_peer_review.py`.

No browser, socket, external publication, real account or live host acceptance
was performed. Real-host decision gates remain in PROVIDER_READINESS.md.
