# Independent adversarial review: final candidate

## Conclusion

The reviewed candidate satisfies the narrow offline independent-peer acceptance model. No recipient-authority bypass was confirmed in the reviewed code or targeted probes. This is not a production security certification, protocol interoperability finding, identity/enrollment validation, native-host trial, or OS isolation claim.

Reviewed SOURCE_MANIFEST.json SHA-256:
`46c50ddac36257ec16d55b2a60d96f7bbe432726470de3492de2848a96972013`.
All 18 covered source, test and documentation files matched before final execution. The exact file hashes are retained in evidence/independent-final-manifest-verification.log.

## Independent process evidence

Ten independent unittest methods passed with ResourceWarning promoted to an error. These use a genuine ordinary Alice subprocess and a test-owned malicious Bob identity outside the victim. No victim private key export or debug command was added. They establish:

1. Valid sender signatures cannot invent Alice's locally authorized outgoing request.
2. Fresh sender signatures over an old recipient grant do not survive revoke/regrant; the replacement grant can be accepted.
3. Legitimately signed wrong phase, scope, processor identity, request ID and domain evidence is rejected.
4. Exact received bytes replay after cancellation returns historical receipt only, while processing, changed bytes and new message admission remain blocked.
5. Historical authenticated processing claims do not revive revoked local receive authority.
6. Rejected control commands on peer ingress cannot change dispatch lane or owner state.
7. An incomplete peer-lane owner command cannot cross into owner dispatch; EOF terminates without cancellation mutation.
8. A storage abort between result inbox insertion and outgoing-proof update rolls back both writes in the actual receiver process.
9. Client timeout now closes both lanes and reaps the child on the tested path, retaining outcome uncertainty and preventing route reuse.
10. Exact approved-and-released packet replay is explicitly historical before cancellation and blocked after cancellation, as is packet retrieval.

Final evidence is evidence/independent-final-probes.log. The bundled 45-test aggregate and fictional demo were independently rerun; see evidence/independent-final-aggregate.log. These are distinct suites, not a claim of 55 unique security properties.

## Findings and resolution

- Earlier client timeout poisoned the wrapper without stopping its child. A real-child reproduction showed the lower-trust peer lane could still accept a valid result under existing consent. This was a lifecycle/claim gap, not a demonstrated consent bypass. The original probe is retained as evidence/original-poison-probe.py.txt, with output in evidence/independent-poison-lifecycle-initial.log. The text file is historical evidence, not a passing regression on the fixed code. The final wrapper attempts bounded shutdown/reaping and records cleanup uncertainty rather than asserting success. The new regression verifies successful shutdown on the normal tested path.
- Earlier exact approve_send owner-operation replay could return a packet after terminal cancellation even though packet retrieval was fenced. Code review identified the inconsistency; packet-bearing replay was fenced. The final independent regression verifies that fence. No separate original execution failure was recorded for this code-review finding.
- Earlier error text suggested retained-state inspection despite fixture temporary-state deletion. Final docs and error wording now accurately state ephemeral deletion and unresolved outcomes.

## Documentation and remaining boundaries

The final docs accurately describe privileged synthetic owner pipes, a supervisor controlling both fictional owners, same-user filesystem/process access outside the security claim, current recipient grants with no clock expiry, exact regrant fencing, and memory-only keys with occupied-store restart refusal.

approve_send combines exact approval and release; it is not a queue/dispatch stage. Cancellation cannot recall already released bytes. Historical grant/evidence replay does not reactivate policy. The opaque context identifies task scope, not commitment to question text or recipient preview. Processing evidence is an authenticated endpoint claim: a malicious peer can lie about its own processing, but still cannot supply the recipient's missing local request or override the recipient's current policy.

Resource budgets are framing/I/O bounds, not CPU/SQLite/OS isolation guarantees. The custom cryptographic envelope has no demonstrated A4A compatibility, forward secrecy, complete metadata privacy, durable recovery or external-action semantics. The experiment remains one bounded request/result pair per incarnation. No broader identity infrastructure is required to make this fictional fixture meaningful, and none is claimed.

No v29 source or historical ZIP was changed. After review, the ten independent tests were copied unchanged into tests/test_independent_review.py for aggregate execution. Runtime code was not changed; documentation and the final manifest were refreshed to include this review and its tests. The 18-file manifest above identifies the independently reviewed pre-integration snapshot, not the final combined artifact manifest.
