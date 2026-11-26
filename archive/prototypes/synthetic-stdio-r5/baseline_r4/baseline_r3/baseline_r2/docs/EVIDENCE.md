# Evidence and review status

This is a targeted architectural experiment, not a claim of complete security or
a substitute for the frozen v29 regression suite. No original prototype source or
old ZIP was copied or modified. This implementation uses its own experimental
format and has no protocol-interoperability claim.

## Reproducible commands

```sh
PYTHONDONTWRITEBYTECODE=1 python run_checks.py
PYTHONDONTWRITEBYTECODE=1 python -m independent_peer.demo
```

The aggregate command verifies all source-manifest hashes before tests, runs the
55 targeted test methods (45 implementation plus 10 independent review) (many include multiple adversarial cases), then runs the
fictional demo. It requires the existing Python/cryptography dependency recorded
in the README. No package install, browser, network, listener or real identity is
used. All child processes use anonymous inherited pipes.

## Coverage map

- `IndependentProcessTests`: separate PIDs/stores/public key identities;
  receipt versus processed projection; result-before-standalone-proof ordering;
  Bob's own processed-request prerequisite; closed peer routes; queued stale grant;
  revoke/regrant; revoked pending processing; local cancellation and late result;
  explicit refusal; exact replay; dropped receipts/processing proofs; owner operation
  ID collision; domain swaps; occupied-store reopen refusal; sender cancellation
  cannot recall already released bytes.
- `MaliciousSenderTests`: a separate deliberately malicious Bob process has its own
  legitimate private keys and can sign arbitrary test bodies, bypassing Bob's
  ordinary sender policy. Alice still rejects unsolicited results, wrong task,
  context, capability/version, direction, kind, request ID/digest, malformed proof,
  payload bounds, stale local consent, same-ID mutation and re-encryption. Other
  tests reject validly signed evidence with wrong exact binding. A limit test
  deliberately demonstrates that a key holder can lie about its own processing.
- `TransactionTests`: injected before-commit failure rolls back configuration,
  consent, outgoing messages, processing and operation records; an SQL abort leaves
  no partially accepted inbox message.
- `ParserTests` / `CryptoPacketTests`: strict encoding/shape/depth bounds and
  ciphertext/nonce/ephemeral key/protocol/direction/binding tampering.
- `PipeTests`: oversized/zero/malformed frames, EOF, partial frame deadline, slow
  drip cannot reset its deadline, unread peer replies allow owner cancellation
  before finite endpoint termination, lost owner response after committed approval,
  and poisoned clients never automatically retry.
- `LifecycleTests`: minimal environment; malformed response poisoning plus endpoint
  shutdown; same-lane concurrent-call rejection; constructor-failure child reaping;
  all-peer/temp cleanup despite one failure; idempotent descriptor cleanup; packet
  replay fenced after cancel; historical grant replay cannot reactivate consent.

The deterministic pipe-backpressure test uses Linux pipe capacity control. On a
platform without `fcntl`, it reports an explicit skip; a skipped test is not evidence
of that property on that platform. The provided Linux run exercises it.

## Logs and limits

The `evidence/` directory retains initial and later test runs rather than silently
replacing early output. Initial 23-test state coverage passed; subsequent 35-test
transport and 43-test lifecycle iterations passed; the 45-test candidate passed.
`aggregate-checks.txt` records the frozen-source aggregate run. Test counts identify
methods, not a percentage of protocol completeness or assurance.

Ten independently authored real-process probes are included unchanged in
tests/test_independent_review.py. They cover malicious valid signers, stale local
grants, phase/scope proof confusion, terminal replay, revoked-authority claims,
peer/owner lane separation, atomic result admission, timeout shutdown and cancelled
packet export. They were reviewed separately against the 18-file implementation
snapshot, then added to the aggregate without changing runtime code.
See docs/INDEPENDENT_REVIEW.md and evidence/independent-* for findings, original
reproduction and final reruns. Final artifact verification is recorded separately
in verification-r1.json and evidence/fresh-archive-r1.txt. All work
remains experimental even after targeted review. There was no live peer deployment,
external interoperability test, human-consent validation, multi-user OS isolation,
persistent key recovery, production resource test, or metadata-privacy audit.
