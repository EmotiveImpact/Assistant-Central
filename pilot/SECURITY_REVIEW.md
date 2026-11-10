# Pilot adversarial review

This review covers the new two-assistant pilot, separately from the frozen
consent/protocol fixtures and the earlier shared-database acceptance rehearsal.
It uses fictional identities and content. It does not establish independent
third-party security certification, a live provider result or a real-person pilot.

## Authority model under review

- A local password session authorises only the owner and assistant enrolled in
  that private runtime directory. Peer packets never become owner sessions.
- Each owner has a distinct store and signing/encryption identity. Peer trust is
  pinned explicitly by public-key fingerprint, not accepted from message labels.
- Source release, recipient acceptance and provider disclosure remain distinct
  decisions over exact immutable content and destinations.
- A transport receipt establishes stored delivery only. It cannot establish owner
  acceptance, task execution or successful provider work.
- Input and output text is inert. It is never a script, HTML, tool instruction or
  permission to contact an additional recipient.

## Boundaries that remain material

Two processes running as the same operating-system user do not establish hostile
process isolation. That user can read another process's files or memory where the
OS permits it. Password-encrypted keys and private file permissions reduce
accidental exposure; they do not defend an unlocked runtime against its own host.
Independent machines/accounts and deployment security need separate verification.

The pilot's source-origin statement is an authenticated sender declaration, not
semantic proof that content contains no copied or undeclared source. Shared-team
lineage hashes and arbitrary upstream owner labels are insufficient evidence of
remote source consent. Unsupported inherited-source claims must be rejected.

Revocation cannot be globally instantaneous across separate stores. A recipient
may accept an unexpired proposal before a delayed cancellation arrives. Local
cancel request, authenticated remote observation and historical acceptance must
remain distinct. Expiry bounds the validity of unobserved withdrawal; cancellation
cannot recall content already exposed or prove external work stopped.

The initial HTTP deployment is loopback-only. It is not an internet-facing service.
Browser origin checks, exact Host checks, bearer sessions, bounded requests and
quarantine limits are still required against local web attacks and packet abuse.

## Findings and verified repairs

An agent separate from the implementation authors reviewed the actual Python and
browser code, supplied reproductions to the authors and wrote the tests in
`tests/test_security_review.py`. This is an independent review within the same
engineering exercise, not an external security audit.

| Finding | Reproduction and repair |
| --- | --- |
| A signed sender could revive a rejected logical task by changing timestamps and resealing it under a new proposal ID. | Reproduced a rejected original followed by a new pending alias. Incoming admission now enforces the logical route as well as the exact proposal digest. Cancellation tombstones also bind that route. The independent rejection/cancellation rewrap regression passes. |
| Session revocation could interleave after provider authorisation but before the durable dispatch claim. | Provider transactions now hold the owner's revocation-serialised session guard through commit. An independent real-session threaded regression proves logout waits for the claim, and that the guard is released before the fixture transport runs. Logout completed before a claim prevents dispatch. |
| Source or local provider approval could expire while the request was being constructed. | Dispatch now revalidates current source permission, exact request and local approval immediately before committing the claim. Controlled-clock tests cover both deadlines expiring and a shorter source deadline while the local approval remains valid. Both leave no claim and make no provider call. |
| HTTP handlers and receipt accumulation needed explicit resource bounds. | The server now bounds concurrent handlers, request size, quarantine size, receipt outbox size and synchronisation batches. Independent HTTP tests verify quarantine saturation does not evict existing packets and exact duplicates do not consume new slots. |
| The UI interpreted peer revocation and permitted endpoint forms differently from the server. | The UI now requires an explicitly active peer and the same exact loopback endpoint syntax. The UI author's peer-state regression covers the corrected rendering and selection behaviour. |

The static module route was also corrected during review and is exercised by the
independent HTTP suite. No unresolved authority bypass was reproduced in the
reviewed synthetic loopback scope after these repairs. This is not a claim that
all possible defects have been excluded.

## Verification record

On 10 November 2026, the following command passed **34 independent tests**:

```sh
python -B -m unittest pilot.tests.test_security_review -v
```

The tests create distinct private owner directories, real encrypted key vaults
and sessions, actual signed/encrypted packets and real runtime databases. HTTP
tests start the actual loopback server; provider tests use an in-memory synthetic
fixture transport. No live provider, real personal data or external security
scanner is used.

| Area | Tests | Evidence |
| --- | ---: | --- |
| Identity and encrypted delivery | 14 | Cross-owner session denial; restart invalidation; password/token absence from the database; identity pin immutability; signature, direction, context and ciphertext binding; unknown sender denial; conflicting replay; exact retransmission and uncertainty; receipt versus acceptance; cancellation and transaction rollback. |
| Runtime authority | 6 | Rejected/cancelled logical task replay; forged upstream permission denial; cancellation arriving before a proposal; preserved historical acceptance; third-peer decision forgery denial; absence of provider permission despite task acceptance. |
| Actual HTTP boundary | 8 | Exact Host/Origin; strict JSON and fields; bearer requirements and logout; quarantine versus authenticated admission; mailbox quota/deduplication; static content policy and route protection; endpoint restrictions. |
| Provider composition | 6 | Pre-claim logout; revocation serialisation through commit; local and source expiry crossing request construction; cancellation before claim; retained uncertain outcomes without redispatch after adapter restart. |

The implementation authors' broader module suites and two-process demo have
separate records. The local Chromium environment could not create its required
Unix sockets, and the cloud browser could not reach the executor's loopback
listener. Hosted Chromium subsequently passed against the actual owner HTTP
service, including exact accept/reject decisions and desktop/mobile layouts.
The [verification record](VERIFICATION.md) identifies the tested commit, workflow
and screenshots. This is synthetic browser evidence, not real-person enrolment.

## Subsequent engineering gates

- Verify distinct operating-system accounts or hosts, restricted filesystem and
  process access, encrypted transport deployment, backups and recovery. The
  present loopback service and private directories are not hostile-host isolation.
- Establish real-person identity enrolment, fingerprint exchange, lost-key
  recovery, rotation and independently verified peer revocation. Local passwords
  prove control of a configured vault, not a person's identity or informed consent.
- Review the custom encrypted envelope protocol externally and define operational
  key rotation and replay retention. Encryption and signatures here do not imply
  an audited messaging protocol or forward secrecy.
- Extend source authority only with independently verifiable upstream grants and
  exact lineage. A signed self-origin declaration cannot establish semantic
  provenance, and the pilot intentionally rejects arbitrary inherited grants.
- Define distributed cancellation timing and reconciliation for offline peers.
  Retained uncertain delivery or provider outcomes require inspection of the
  original operation; a new operation is not a safe automatic retry.
- Verify live provider account ownership, protected credentials, billing/currency
  limits, current data handling terms, model support and an explicitly approved
  bounded request. The adapter's request/token limits do not establish a spending
  guarantee. The HTTP pilot has no live provider route, and no live result is
  claimed.
- Complete a supervised pilot with independently enrolled participants before
  any real personal information is introduced.

An unauthenticated local process can still consume the bounded quarantine or
available connection slots. These limits constrain resource use; they do not
provide availability against an attacker controlling the host. The browser's
in-memory bearer is similarly within the trust boundary of that browser and its
extensions. No real deployment should infer stronger isolation from this pilot.
