# Offline proposal facade candidate r2

This directory is an additive candidate, not a replacement for frozen r1 or v29.
All copied r1 files and evidence remain unchanged. `run_checks.py` continues to
verify and test only r1; the candidate has separate commands below. No excluded
concurrency/shutdown/descriptor-lifecycle audit was performed or cleared.

## Authority and exact meaning

Trusted composition constructs one ProposalStore file per actor, bound durably to
schema `offline-exact-text-proposal/1`, actor, exact task and both complete public
endpoint descriptors (including incarnations). A reopened store rejects changed
binding. These are plaintext local proposal records, not encrypted storage or a
persistent-key recovery scheme. Endpoint identities remain disposable r1 identities.

The model sees exactly AssistantFacade.propose({text}), status({proposal_id}), and
processed_inbox({}). No actor/task/owner selector, raw lane, grant, packet, private
key or privileged callback is exposed. Proposal submission writes only its local
proposal SQLite file, never endpoint state. This is a logical dispatch boundary:
trusted host code must expose only these methods. Arbitrary Python object access,
the OS user and the supervisor remain trusted; Python privacy is not isolation.

Text is unsigned exact nonempty Unicode scalar text, at most 1024 UTF-8 bytes.
Whitespace is significant; there is no normalization, truncation, code execution,
JSON stringification or user-selectable fresh identifier. The proposal ID commits
the entire fixed binding and exact text; content_digest separately commits text.
Repeat exact content returns the same durable record, including declines,
rejections and uncertainty. Maximum 64 records, with no eviction/reset operation.
A full store refuses new meanings but still returns historical duplicates.

## Explicit owner workflow, no dispatcher

OwnerReview is a separate trusted API, not exposed to the assistant. Review shows
exact text, binding, content digest, selected grant and grant digest. Explicit
prepare_approve_and_release checks those digests, validates the recipient-signed
grant's scope/bindings, generates one operation ID and persists `unknown` plus the
exact command digest BEFORE returning the detached owner command. Only the trusted
caller may execute that exact command manually. Returning a command is not proof
of execution. The API never retries, returns the command again, resets unknown,
or approves a duplicate under a fresh ID, even after known rejection.

A returned command is a detached dictionary, not a tamper-proof execution token.
A malicious trusted caller can change it or issue unrelated owner commands. The
host must execute the reviewed command exactly. A modified return value cannot
change the stored reviewed meaning or command digest. This candidate does not
claim to constrain the privileged owner or authenticate a human owner.

States:
- pending: unsigned local proposal only.
- declined: exact local owner refusal; repeat stays declined.
- unknown: command prepared; execution and packet release not known locally.
- rejected: trusted caller attests an actual endpoint Rejected response for the
  exact operation/command. Generic errors, malformed responses, timeouts and
  silence cannot establish rejection. Never retry under this proposal.
- released: trusted caller recorded the actual successful initial approve_send
  response for the exact operation/command. Packet hash, message ID and digest
  correlate disclosure; peer receipt and processing remain unknown.
- committed_content_observed: an actual fixed local snapshot contains the exact
  outgoing content. The prepared attempt's operation causation, packet export and
  delivery remain UNKNOWN; this is not successful resolution or a retry permit.
  This observation is terminal in r2: even a later actual response or rejection
  cannot enrich it. That is a deliberate conservative evidence-retention
  limitation, not resolution of the underlying uncertainty.

Recording is a trusted attestation boundary, not response signature validation.
record_response accepts separately obtained actual endpoint response, never a
callback or fabricated model claim. It stores only allowlisted opaque correlators,
not the packet. Before recording success, public packet/header shape, protocol,
direction, both descriptor digests and canonical ephemeral/nonce/ciphertext encoding
are checked (32-byte ephemeral public key, 12-byte nonce, at least a 16-byte GCM
tag). These structural checks do not decrypt/authenticate the inner message or
prove its content/operation correlation. record_rejection likewise requires an actual Rejected response
from the fixed endpoint, not a locally fabricated exception. Caller provenance is
trusted. Correlation IDs/digests do not themselves prove endpoint authenticity.

Snapshot reconciliation cannot prove the prepared operation caused a matching
outbox. r1 has one outgoing slot, so exact-text matching is useful local knowledge,
but it is intentionally labeled only committed_content_observed. Absence is
inconclusive. Cancellation never erases records or unknown outcomes. The store
has no cancellation/regrant/revoke/send/process operation at all.

## Processed-only local knowledge

SnapshotPublisher is separately privileged. It accepts the actual inspect response
obtained through fixed trusted composition, validates actor and exact local public
incarnation, and exposes only id/kind/message_digest/payload from processed_projection
with true processed evidence flag. It never reads payloads from raw incoming or
outgoing into the assistant inbox. Snapshot does not contain task or peer binding;
those rely on the fixed trusted endpoint connection, not independent verification
by the publisher. Fabricated snapshots supplied by trusted code are out of model.

Never-published (publication=0) differs from published-empty (positive revision).
Revisions increase. Detached snapshots/results prevent caller reference mutations.
A published processed item cannot be erased/replaced by a stale snapshot or after
cancel. Views explicitly say last trusted-published local knowledge, not fresh
network truth. Processing is an endpoint state claim, not proof of human/model
work or an external effect. Incoming text remains untrusted data, never authority.

## Scope conversion and migration

No v29 import, wire or state migration is implemented. v29's 512-codepoint bounds,
resource shortlists, composed tasks, workspace/grouping, generic capabilities,
owner-signing separation and submit/dispatch states are unsupported. Do not map
v29 task/request digests to r1 scope/message digests or treat `released` as v29
submit/delivery. There is one fixed Alice request/Bob result pair per incarnation.
Fresh endpoint identities cannot adopt an old proposal store. An explicit future
migration design would be needed; deleting old records is not migration.

## Run independently

From candidate root:

    PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s facade_tests -v
    PYTHONDONTWRITEBYTECODE=1 python -m facade_candidate.demo
    PYTHONDONTWRITEBYTECODE=1 python run_checks.py

The demo uses two existing endpoint processes and four independent stores (two
endpoint stores plus two proposal files). All grant, release, delivery and process
calls are explicit synthetic trusted-owner/fixture steps. No assistant callback
performs them. No live traffic, sockets, listeners, credentials, enrollment,
installation, browser or native-host changes are part of this candidate.
