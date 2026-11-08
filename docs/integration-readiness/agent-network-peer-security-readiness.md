# Peer security guarantees and the first real two-owner pilot

Static review, 2026-11-08 UTC. Frozen inputs: independent-peer r1, facade r2,
MCP r3, raw framing r4, and synthetic stdio r5. This report changes none of them.

## Decision

The next important work is establishing **who controls each endpoint and what an
observer can see**, not adding another cipher or counting more synthetic tests.

The inspected protocol coherently binds messages, grants and evidence to the
configured endpoint descriptors. No cryptographic authenticity bypass was found
within its stated trusted-bootstrap, single-task model. This is a static finding,
not a cryptographic proof, fresh test result or production endorsement.

Three decisions block a meaningful real two-owner exchange:

1. **Owner and key provenance:** which two people control the endpoints, how each
   verifies the other's complete session descriptor, and what authenticates local
   approval. A label such as `bob`, a host name or an MCP connection is insufficient.
2. **Control-plane confidentiality:** which channel carries descriptors, grants,
   packets and evidence, and which parties/providers can see each object. Clear
   evidence plus clear grants can reveal low-entropy encrypted payloads by guessing.
3. **One-session or persistent service:** a disposable, manually approved session
   can defer persistent identity/recovery. A continuing relationship cannot. The
   current implementation deliberately cannot resume with its old identity.

The smallest worthwhile milestone is one synthetic request/result between two
independently controlled, already-accepted native hosts using different providers,
with both humans approving exact outgoing content. That is a future pilot with a
new reviewed composition and explicit authorization, not something r5 can do now.

## Scope and evidence limits

Inspected application/cipher source: r1 `independent_peer/protocol.py`, r1
`independent_peer/endpoint.py`, and r2 `facade_candidate/store.py`. Referenced
README/DESIGN and integration reports are listed with hashes below. The r1
protocol and endpoint files copied into r2 have identical hashes.

No prototype module, runner or test was imported or executed. No Identity,
Endpoint or owner instance was constructed. No keys, credentials, host setup,
installation, browser, network connection/listener or external communication were
used. Frozen artifacts were read or hashed only. Runtime claims from earlier
reports remain historical evidence, not checks performed by this review.

The additional peer-process cross-lane concurrency, shutdown,
descriptor-reuse and associated revoke/cancel interleaving audit remains excluded
and uncompleted. `fixture.py`, `pipes.py` and `worker.py` implementation internals
were not read or tested. Nothing here substitutes for that audit, establishes its
outcome or authorizes repeating it. No process/lifecycle acceptance is inferred.

## 1. New privacy finding: plaintext guessing through evidence

**Classification:** conditional integration defect if the current control objects
are exposed to an untrusted relay while claiming that relay cannot learn payloads.
Not an exploit against the current trusted local supervisor, and not an AES-GCM
or SHA-256 break. No external relay is implemented or was contacted.

### Exact source path

- `endpoint.py:67–71`: received/processed evidence includes the message ID, full
  scope, `message_digest = digest(body)` and `grant_digest = digest(body['grant'])`.
- `endpoint.py:129–135`: admission returns the signed receipt directly, without
  an encrypted evidence envelope.
- `endpoint.py:223–230`: `allow_receive` returns the complete signed grant.
- `endpoint.py:243–245`: the request plaintext body has exactly `id`, `scope`,
  `grant`, `request` and `payload`, with the request link set to null for Alice.
- `protocol.py:34–39,93–94`: `digest` is unkeyed SHA-256 of deterministic JSON.

### Static derivation

Suppose an observer sees a request's complete signed recipient grant G and the
signed `received` proof. Let R = received["body"], the proof's clear evidence body, not its outer
`body`/`signature` wrapper. This would be true of a relay carrying those existing
API objects in clear. The observer can confirm `digest(G) == R.grant_digest`,
then construct, for any candidate text c:

    candidate = {
        "id": R.id,
        "scope": R.scope,
        "grant": G,
        "request": null,
        "payload": c
    }

If `digest(candidate) == R.message_digest`, c matches the plaintext request, up to
the ordinary negligible hash-collision probability. Every body field except the
payload is now known. The random grant nonce does not prevent guessing because it
is in G, and the random message ID does not prevent guessing because it is in R.
The sender's message signature is not needed: the digest covers the body, not the
signature or ciphertext. A short choice, time slot or yes/no statement can have a
small candidate space. High-entropy content is not thereby generally recoverable.

If the observer also holds encrypted packet W, `digest(W) == R.packet_digest`
correlates this proof to that exact packet. W consists of `header` and
`ciphertext`; its clear header contains protocol, sender/recipient labels, both
descriptor digests, ephemeral public key and nonce (`protocol.py:181–190`). No
decryption key, nonce reuse, modified packet or signature forgery is required for
the guessing derivation.

The same reasoning applies to a result if the observer also knows the embedded
request link and its full processing proof. The request case alone establishes
the problem; no assumption about the result path is needed.

An observer with only the encrypted packet and receipt, but without the complete
grant or another source of the unknown fields, does **not** automatically have this
verifier. Do not overstate the finding as universal decryption from any receipt.

### Smallest correction proposal

Before introducing an untrusted relay, classify **grants and evidence as potentially
content-revealing**, not merely harmless routing metadata. Keep those complete
objects inside an already-reviewed confidential authenticated channel with the
appropriate visibility/retention contract. If a relay is not allowed to see them,
that channel must protect them end to end, rather than terminate at the relay.
This report does not design another custom encryption scheme.

Minimize exposure before changing cryptography: keep person-to-descriptor mappings
local unless the chosen transfer actually needs them; exchange only the required
grant/packet/evidence objects for that phase; do not send owner snapshots, proposal
databases or full audit logs to a relay. Keep raw grants, proofs and owner commands
out of model tools and third-party analytics. Their current absence from the
three-tool facade is a boundary worth preserving.

Do not remove message/packet/grant bindings from receipts as a quick fix: those
bindings prevent evidence being credited to a different message. Do not replace
the deterministic digest with an ad hoc secret-hash protocol without a separate
design review. A public-synthetic pilot may explicitly permit the transfer service
to see all pilot data, but then it does not validate confidential relay operation.

## 2. Key binding is implemented; owner identity binding is assumed

`protocol.py:127–145` creates a signing key, decryption key, actor label and
incarnation, and validates the descriptor's shape. `endpoint.py:205–212` accepts
the supplied peer descriptor if it is structurally valid and has the other fixed
actor label. No certified identity, owner account, independently verified contact
or proof of a real human's control enters that decision.

Subsequent grants bind the digests of **both complete descriptors**, including
both public keys and incarnations (`protocol.py:172–178`). Outer packets bind the
same descriptors (`181–207`). That is useful pinning to the configured keys. It
does not establish that the configured keys belong to the intended person.

If an attacker controls a future descriptor-discovery/bootstrap step, they can
substitute their own descriptor labelled `bob`; successful downstream signature
checks would authenticate those substituted keys. This is not a bypass of the
current trusted-fixture assumption. It is the reason an unauthenticated directory,
MCP `clientInfo`, model claim, or relay-supplied contact cannot become that trust root.

**Minimum pilot decision:** each human verifies the other endpoint's complete
descriptor fingerprint through a separately authenticated channel they explicitly
choose. Record which person and one session it is verified for. Local composition
must then pin that descriptor and scope. This is a manual single-session identity
decision, not a persistent identity product or automatic proof that the person
controls every agent carrying their name.

The two endpoint owners must not share the current fixture's single approval
authority. Two processes, two database files, two providers, or two account labels
do not by themselves establish two independently controlled owners.

## 3. What the cryptographic composition does and does not support

| Property | Inspected evidence | Defensible interpretation |
| --- | --- | --- |
| Signature domain separation | `protocol.py:136–137,149–156`; endpoint uses `grant`, `message`, `received`, `processed` | A valid receipt signature is not accepted as a processing or grant signature. All domains include the protocol version. |
| Header integrity and context binding | `protocol.py:181–207` | Full canonical header is HKDF info and AES-GCM associated data. Direction and descriptor bindings are checked before opening. Header tampering is not a supported way to redirect a valid packet. |
| Sender authentication | `protocol.py:207`; `endpoint.py:110–121` | AEAD opening alone is not sender authentication: anyone can encrypt to a public X25519 key. The peer's inner Ed25519 signature, followed by application/grant checks, supplies authentication to the pinned signing key. |
| Binding the inner message to the parties | `protocol.py:172–178`; `endpoint.py:113,121,233` | The recipient-signed grant in the signed message binds both full descriptors and exact task/direction. The inner signature does not directly sign the outer header; that omission is not, by itself, a demonstrated rebinding flaw in the composed admission path. |
| Distinct encryption per message | `protocol.py:181–189` | Fresh ephemeral X25519 key and random 96-bit nonce; standard HKDF/AES-GCM primitives. This review did not generate keys or evaluate a production randomness environment. |
| Forward secrecy | `protocol.py:187,201`; r1 DESIGN:196–206 | Absent. A captured ephemeral public key and later compromise of the recipient's static decryption key allow recovery of the shared secret for past packets. Ephemeral sender keys alone do not provide forward secrecy. |
| Scope confinement | `endpoint.py:110–135` | Recipient checks its own expected scope, current stored grant and request linkage. The peer cannot create a local outgoing-request commitment merely by asserting one in a result. |
| Honest peer behavior | `endpoint.py:67–79,89–98` | A processing signature authenticates what that endpoint claims. A malicious peer controlling its signing key can claim processing without doing the work. |

HKDF's absent explicit salt is not identified as a defect here: the construction
uses an ephemeral X25519 shared secret and context-bound info. No unsupported
claim that a salt alone would repair identity, forward secrecy or evidence privacy
is made. The protocol version fixes the suite; no cipher negotiation/downgrade
mechanism was found in the inspected interface.

The JSON signature encoding is the project's deterministic Python JSON encoding,
not an established A4A or general cross-language canonicalization contract.
`ensure_ascii=True`, sorted keys, compact separators, exact schemas and strict
scalar handling are part of its effective wire meaning. Any independently written
peer needs an explicit compatible specification and vectors before interoperability
can be claimed. This review does not supply or execute new cryptographic vectors.

## 4. Consent and status must not be overstated

There are four different facts, each with a different evidence source:

- **Unsigned proposal:** r2 `store.py:80–96` writes exact text and fixed binding to
  its local proposal store. It does not authorize delivery.
- **Owner approval and release:** r1 `endpoint.py:231–249` creates and returns a
  publishable packet through a privileged API. The endpoint signs it with its own
  key. There is no separate cryptographically authenticated human approval in
  that message. r2 `store.py:131–172` trusts the privileged caller to execute the
  exact reviewed command and record the actual response.
- **Received:** a recipient-signed claim about the local persistence event,
  bound to the exact body, original packet and grant. It is neither human review
  nor downstream application work.
- **Processed:** a recipient-signed claim about the local `process` transition,
  not a proof that a model reasoned, a person agreed, or an email/calendar/payment
  action occurred (`endpoint.py:250–260`; r1 DESIGN:143–155).

The same endpoint signing key signs grants, messages and evidence. Domain
separation prevents type substitution; it does **not** separate human authority
from endpoint compromise. The keys cannot establish a stronger owner-approval
provenance than the trusted local owner interface actually supplies.

The inspected README/DESIGN reports already say this correctly. No current
documentation claim that a valid message signature proves real human approval was
found. Labels such as `approved_and_released` and r2's `local owner declined exact
meaning` describe privileged local API transitions under that trust assumption.
They would become misleading if a future UI or peer treated them as independently
authenticated human decisions. Preserve the evidence basis instead of upgrading
those labels during integration.

r2 publication is also a trusted local boundary, not a peer evidence verifier.
`store.py:234–274` checks snapshot actor/incarnation and processed flags, then
publishes selected fields. The snapshot lacks task and peer identity fields;
the fixed authenticated local source must supply that provenance. Moving
SnapshotPublisher or OwnerReview behind an unauthenticated host/model callback
would remove an assumption on which the current design depends.

Incoming consent is to one bounded text message in an opaque scope. It is **not**
recipient approval of the exact question: `protocol.py:159–169` validates a task ID,
context digest and fixed capability, but does not derive the context from question
text. r1 DESIGN:40–43 states this limitation. `snapshot()` withholds unprocessed
incoming payloads (`endpoint.py:263–276`), so the existing owner API also does not
offer a general exact-content preview before the local processing transition.
The first pilot should disclose that consent meaning rather than silently promise
exact-question approval or invent a preview feature as an incidental bridge step.

## 5. Custody, lifetime and visibility decisions

### A disposable session is possible; durable identity is not implemented

Keys are generated in memory (`protocol.py:129–134`). An occupied SQLite store is
refused on a new Endpoint instance (`endpoint.py:17–18`), rather than adopted with
fresh keys. r2 proposal binding also includes both full descriptors and refuses a
different binding on reopen (`store.py:29–50`). Copying a database, reusing `alice`
or creating a new key does not restore the prior peer relationship or resolve an
uncertain old release.

For a first explicitly temporary pilot, choose no restart/recovery promise and
new owner verification for any future run. The session's private keys still need
an owner-controlled trust boundary; a disposable key is not permission to expose
it to a host, model or the other owner. Public RFC fixture descriptors used by r5
must never be promoted to real cryptographic identities.

A longer-lived product must separately decide how an owner/device is enrolled,
where the signer/decryption keys live, who can invoke them, and how loss or
compromise changes contact trust and pending disclosures. Persistent access and
key enrollment require their own authorization. No such design is added here.

### The data path has more than ciphertext

- Outer packet: clear actor labels, descriptor digests, ephemeral public key,
  nonce, protocol and ciphertext length. It permits linkability within that
  descriptor/incarnation and exposes size. Timing/route details depend on the
  eventual transport.
- Grant: task/context/capability, direction, both binding digests, epoch and nonce.
  It is signed, not independently encrypted by the grant API.
- Evidence: clear scope, ID, body/packet/grant digests, processor binding and
  status. Publicly verifiable claims can be forwarded by their recipient.
- Local endpoint/proposal stores: plaintext application/proposal text and proofs.
  A processed-only projection is not at-rest encryption or protection against the
  trusted endpoint/OS user.
- Host/model: processed inbox text, prompts, schemas, tool arguments and results
  may reach that host's provider and logs. Host-to-tool stdio says nothing about
  the model hop being offline or end-to-end confidential from the provider.

Grants have no clock expiry; the current implementation relies on local policy
and disposable session lifetime. A future unattended endpoint would need an
explicit consent lifetime decision. No race, cancellation ordering or shutdown
behavior was investigated to reach that observation.

## 6. MCP, peer wire and A4A are separate acceptance tracks

r3/r4/r5 establish different local tool boundaries. Their three methods remain
`propose`, `proposal_status` and `processed_inbox`. None is peer delivery, owner
authentication, signing, receive consent or processing.

r5 now supplies a real local Python 3.12/POSIX stdio launcher. Its reported 39
checks and SDK-client negotiation are historical local evidence. The older
planning report's statement that no actual launcher exists has been superseded
by r5, but **native-host acceptance is still missing**. r5 constructs neither
endpoint nor owner/publisher objects and accepts only its one exact fixture text.
It cannot be converted into a two-owner system just by changing host settings.

Two different native hosts using the same experimental peer implementation would
demonstrate cross-provider application integration. It would not establish an
independently implemented peer wire, A4A compatibility or a general relationship
network. r1 explicitly uses `independent-peer-experiment/1`, not the pinned A4A
private-message wire used in the older prototype. Sharing X25519 or Ed25519 does
not make protocols interoperable; the envelope, serialization, context and
evidence semantics must all match.

## 7. The smallest meaningful follow-on pilot

This is a decision specification, **not authorization, a launch recipe or a
replacement for the excluded audit**. No current artifact is represented as a
ready two-owner peer service.

### Preconditions

1. Complete the separately approved public-synthetic native-host acceptance on
   the exact selected machine/build. Then establish the equivalent narrow local
   tool path on the second owner's selected host. Do not assume acceptance of one
   host/model provider establishes the other.
2. Choose two real owners, their separate owner-controlled machines/accounts,
   the local approval mechanism and a manually verified session-descriptor
   exchange. Bind the initiator/responder roles explicitly; Alice/Bob are roles,
   not evidence of identity.
3. Review an additive composition that keeps the assistant proposal-only and
   connects owner review, endpoint admission and publication through authenticated
   local authority. This is new work with a new acceptance boundary, not a flag
   to widen r5. Do not use or reroute work to clear the previously excluded
   peer-process audit; any dependency on it remains an unresolved gate.
4. Select one existing authenticated transfer channel and name its exact
   destinations, visibility and retention. For the smallest experiment, owners
   can explicitly transfer the bounded pilot artifacts without building a relay,
   directory, webhook or wake service. This is still external communication that
   needs authorization. It does not certify transport privacy.

### One successful exchange and no expansion

- A fixed public-synthetic question, for example: `How many paper moons are in
  this fictional scene: moon, moon, moon?` Expected result: `Three paper moons.`
  These are proposed future pilot texts, not r5's currently allowed tool text.
- One task with bounded text; recipient consent explicitly covers that single
  task/peer/direction. Each host only proposes local text. Each human reviews the
  exact outgoing payload and intended recipient and explicitly approves release.
- The recipient's own endpoint admits the packet and returns receipt evidence.
  Its owner separately controls processing and local publication. Only after
  that publication may its host read the peer text through processed_inbox.
- The responder host proposes the short result; its owner approves exact release.
  The initiator checks the local request linkage, then separately processes and
  publishes the result. Record exact released-packet/evidence correlations and
  each host's observed restricted result.
- Stop after that pair. No real personal data, standing relationship permission,
  arbitrary tools, autonomous sending, automatic retry/restart, subscription,
  ongoing listener or persistent identity claim. Any uncertain outcome stays
  uncertain; a fresh session is not proof the old disclosure did not occur.

Success means: **two independently controlled owners used two accepted host/provider
paths for one scoped synthetic exchange, with recipient-owned admission and explicit
human release on both sides.** It does not mean secure anonymous relay operation,
forward secrecy, external-effect proof, persistent identity, remote cancellation,
production process isolation, wake, A4A compatibility or arbitrary agent networking.

### Exact approval package required before doing that work

Ask for, and record, the following concrete choices rather than “connect the agents”:

- Both owner names and explicitly named host agents, provider/accounts, machines,
  OS/builds, and who approves each local call and each outgoing release.
- The exact peer contact/account or endpoint destinations and the authenticated
  descriptor-verification channel; which full descriptors/fingerprints are being
  accepted for this single session.
- The two exact synthetic texts and the complete categories of exchanged data:
  public descriptors, task/scope, grants, encrypted packets, signed evidence,
  processed text and correlation/status metadata. Identify which owners, transfer
  service and host/model providers can receive each category.
- The reviewed code/runtime and precise temporary configuration/access changes,
  session lifetime, intended local/provider retention and bounded rollback.
  Unexpected credentials, enrollment, persistent access, installation, terms or
  broader permissions need the applicable new approval. Rollback cannot erase
  copies or provider history already created.

Both people must authorize their own endpoint participation. The user's approval
alone cannot authenticate or confer authority over the other person's agent.
Do not treat agreement to native MCP testing as agreement to this later peer exchange.

## 8. Preservation and source record

Only this new report and its new hash sidecar were written. Source and archive
hashes below are reproducibility anchors, not proof of identity, artifact signing,
production safety or the truth of every earlier test claim. The final check
compares these named inputs against the values recorded during this review.

| Input | SHA-256 |
| --- | --- |
| `agent-network-independent-peer-experiment/independent_peer/protocol.py` | `1b01582e201f7e6b9e6b54d25cb0a080e48fb66fb9e69a9eee727afdba561516` |
| `agent-network-independent-peer-experiment/independent_peer/endpoint.py` | `4e2ff7458c0d72fc7133fdda18eea6d4fabb8885a4ad0dda5a5ded16eec49da0` |
| `agent-network-independent-peer-experiment/README.md` | `e505ea337fc200cf9ec60e53551bd644533873b0f76ede24084c871f8ce4ceba` |
| `agent-network-independent-peer-experiment/docs/DESIGN.md` | `34978a24352cec43505b05ea1bac408bfda622888e64cc8cd0c1c354608a7c29` |
| `agent-network-independent-peer-facade-r2/independent_peer/protocol.py` | `1b01582e201f7e6b9e6b54d25cb0a080e48fb66fb9e69a9eee727afdba561516` |
| `agent-network-independent-peer-facade-r2/independent_peer/endpoint.py` | `4e2ff7458c0d72fc7133fdda18eea6d4fabb8885a4ad0dda5a5ded16eec49da0` |
| `agent-network-independent-peer-facade-r2/facade_candidate/store.py` | `a7586e91b49e2e1d64d973a5b2ffc3ba8f1402b2984bcc5ec91145f9d1e89a54` |
| `agent-network-independent-peer-facade-r2/facade_candidate/DESIGN.md` | `633f5f73687925f93e4cc14fd8429ce7dbf75fd181d522a4d4e8ad063c67f67a` |
| `agent-network-independent-peer-facade-r2/README.md` | `e505ea337fc200cf9ec60e53551bd644533873b0f76ede24084c871f8ce4ceba` |
| `agent-network-independent-peer-mcp-r3/DESIGN.md` | `1ca67ca2eff2bbe43fcf5e6e2ab474d79002ac2b7dd0c07c9abd7bd2a36d92ad` |
| `agent-network-independent-peer-raw-r4/DESIGN.md` | `7c8ae19a6477dedfaaaa2575ec1a757a55233c672a46c418872f83ff3309fef8` |
| `agent-network-synthetic-stdio-r5/README.md` | `9032af66ff3fdbac79d37b217e27aa34a44ed85f990cf4b7e646f9f183a6c8b3` |
| `agent-network-synthetic-stdio-r5/START_HERE_R5.md` | `9f7c9e9143adade55681b8b97e6dd56a8e28f4ffdc705013d9baa87a5750af8b` |
| `agent-network-synthetic-stdio-r5/EVIDENCE.md` | `d777b229eec4c9efebf5e5ee00a7a3fcd5a394c8dd52b039254907808d0ab5eb` |
| `agent-network-v29-architecture-integration-audit.md` | `a5c5ea86fb75075ebc44706945719506f792a52a13c9a30b412774c549676cdb` |
| `agent-network-v29-r1-integration-design.md` | `08b5ed4c6180a9e4ec313ae7612b54e5b43ae4b00a18e039a8fa76c8ae8bc296` |
| `agent-network-minimal-real-pilot-plan.md` | `200bdd7230a566697233a49325bc409111636d4b91551ecfc8fc800d3fd2ec67` |
| `agent-network-pilot-host-verification.md` | `f2ef2538848f1e460a69146116d8aa2763735bf3d137ee1ada2b2c2ed0b29d20` |
| `agent-network-independent-peers-experimental-r1.zip` | `9a6fb0140c6b1edb6ccfd30a3a98e7983f5bec12e0615b1aad1d1a765d279a14` |
| `agent-network-independent-peers-experimental-r2.zip` | `1c7dc0bffde1b9a5e06113394e17a3a1948d95e3721d094f06fbdeb557358413` |
| `agent-network-independent-peers-experimental-r3.zip` | `b4f0b6b5b84c19b8c1fba05f4df7ecd1bd05fbddb47427cfa95b1be547b99a94` |
| `agent-network-independent-peers-experimental-r4.zip` | `27176f8b69dbfec478327c40b8574ddd973258ea48a8b9542127725e0b80ac67` |
| `agent-network-synthetic-stdio-experimental-r5.zip` | `050d8d91a06f683a40d7ef7b9ab76e7f46238e2db8313b106bf6b353abef2d88` |

Preservation check: all 23 named inputs were rehashed after report creation and matched this sidecar. No frozen input was written.
