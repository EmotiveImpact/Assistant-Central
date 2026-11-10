# Roadmap

## Current implementation

Python remains the current orchestration and experimentation language. The team
coordinator, consent/protocol prototype and synthetic MCP stdio launcher are
separately tested. The new [offline binding](integration/README.md) maps exact
accepted team artifacts to unsigned local proposals through recovered wire
building blocks. It is not an end-to-end connected network.
The [execution ledger](execution/README.md) now binds one started team task to one
synthetic dispatch claim, retains uncertainty across restart, and reconciles an
original result into the existing artifact review gate. It makes no provider calls.
The [provider disclosure rehearsal](execution/PROVIDER_DISCLOSURE.md) additionally
binds an exact synthetic destination and separate approvals from the task owner
and each direct/upstream input owner, atomically with that execution fence.
Retained task-input ancestry now preserves original owners across derived
artifacts and rechecks historical disclosure withdrawal. Those fictional local
controls are not authenticated owner approval, semantic data tracking or live
provider authority.
The [recipient acceptance rehearsal](integration/RECIPIENT_ACCEPTANCE.md) now adds
an explicit one-shot synthetic release and a separate recipient accept/reject
decision over the exact staged artifact. Current source rights, inherited
permissions, terminal decisions, expiry and restart uncertainty are checked in
the shared team transaction. Recipient work still requires its own approval.

The [two-assistant pilot](pilot/README.md) now implements all five follow-on local
workstreams: password-authenticated owner sessions and encrypted keys, separate
runtime stores/processes, pinned encrypted peer delivery with durable receipts,
a disabled-by-default OpenAI Responses adapter, and a browser owner workspace.
Its actual loopback exchange tests cover task acceptance, origin-only artifact
return, rejection, cancellation and restart. No real owner enrolment or live
provider acceptance is claimed. The fictional shared-team decisions are not
treated as authenticated source consent.

The [reviewed work loop](pilot/WORKFLOW.md) now connects accepted input to a
separately approved synthetic fixture run, retains the original result, and
atomically stages one exact return-artifact draft after result review. Release
and requester acceptance remain separate. It tests offline delivery and restart
on the same pinned loopback address; it performs no actual model work or research.
The next useful-work milestone still requires separately controlled hosts and a
reviewed, explicitly approved live provider integration.

## Next engineering gates

1. Review the new local pilot and verify deployment under separately controlled
   OS accounts/devices. Same-UID process tests do not establish hostile-owner
   isolation. A reviewed carrier is needed beyond the current loopback listener.
2. Enrol two real owners explicitly, verify peer fingerprints independently and
   exercise the actual approval/rejection/cancellation interface. Keep model tools
   separate from owner controls and private sessions separate from shared results.
3. Verify one named provider account using synthetic input, exact source/recipient
   approvals, billing/data policy and privately supplied credentials. The adapter
   code exists; live provider and native-host acceptance remain unverified.
4. Complete key rotation/recovery, retention/deletion, backup rollback and incident
   handling contracts. The pilot encrypts identity keys but stores local application
   text in private unencrypted files. Obtain external security review before real data.
5. Validate remote delivery, reconnect and cancellation under real outages. Local
   tests prove bounded original-packet retries and durable dedup; provider requests
   remain single-attempt. Remote cancellation takes effect when observed and cannot
   prove immediate recall or remote shutdown. General inherited-source forwarding
   still needs independently verifiable upstream owner grants.
6. Measure realistic workloads and failure modes before making scale, throughput
   or reliability claims. Keep compatibility, observability and operational
   complexity visible alongside performance.

The first usable network milestone is a two-person pilot: each person controls
their own assistant, one exact task and artifact cross the boundary, and both can
inspect approval, rejection, cancellation and recovery history. Authenticate the
owners and validate the isolated synthetic exchange before introducing real data.

## Rust remains an option

Evaluate Rust for bounded message validation, cryptographic boundary components
or measured throughput bottlenecks. A rewrite is not assumed. A candidate must
demonstrate interoperability with Python, a simpler or defensible operational
model, reproducible performance results, maintainable interfaces and security
review. Memory safety does not replace authentication, consent or key custody.

## Reuse research

Evaluate orchestration frameworks, durable workflow engines and secure messaging
projects separately. Existing libraries can help with execution adapters,
checkpointing and transport, but none should silently become the authority for
another human owner's actions. Preserve upstream notices and review license
obligations before code reuse, especially copyleft distribution boundaries.

The [source-linked landscape review](docs/research/orchestration-landscape.md)
compares 14 main candidates and 7 alternatives. Evaluate a minimal stack: keep
owner control independent, consider LangGraph for coordination and Pydantic AI
for a Python runtime adapter, use DSH Squad as a receiver-authority design
reference, and assess A4A/A2A at their separate transport/protocol boundaries.
These are research recommendations, not selected dependencies or tested integrations.
