# Independent application-contract review, candidate r2

Scope: new proposal facade and its application contract only. Reviewed store.py,
demo.py, DESIGN.md, test_facade.py and the relevant frozen endpoint/protocol API.
No fixture.py, pipes.py, worker.py, concurrency, shutdown or descriptor-lifecycle
review or test was performed. That excluded audit remains unresolved.

## Findings

No blocking application-authority defect found within the documented trusted
composition boundary. Exactly three assistant methods expose unsigned proposals,
limited local status and historical published processed input. The store is not
an OS isolation boundary. Trusted owner/publisher callers can fabricate responses
or snapshots; the candidate explicitly disclaims protection against those callers.

Unknown is durably recorded before a prepared command is returned; even a command
never executed cannot be prepared again. Exact-content IDs include fixed binding,
and declined/unknown history survives reopen and a full 64-record store. Released
means a trusted caller recorded endpoint release, not delivery. Snapshot-only
reconciliation correctly labels committed content without claiming operation
causation or release. Recipient processing remains distinct from persistence.

Snapshot publication checks local actor/incarnation, not task or peer binding,
because the frozen endpoint snapshot lacks those fields. Fixed trusted composition
is necessary. Historical processed content cannot be replaced or erased through
publication. This is not a native-host registration or authentication test.

Parent-requested defense-in-depth corrections are reviewed: returned-packet
structural binding validation rejects foreign public headers, and constructor
initialization failures close the local proposal-store SQLite connection. These
checks do not authenticate response provenance or decrypted message contents.

One conservative limitation remains: committed_content_observed is terminal in
r2. Even a later actual response or rejection cannot enrich that record. An
independent regression demonstrates the late-response rejection. This loses useful
evidence enrichment, but does not create an authority bypass or mislabel release.
Final DESIGN now documents it explicitly; content observation is not uncertainty resolution.
A future enrichment transition need not grant retry permission.

## Independent evidence

Eleven independent tests pass in test_independent_contract.py. These use ordinary
Endpoint objects sequentially in one Python process and temporary SQLite files;
no process transport is involved. Coverage: actual release without peer delivery;
unknown durability before any execution; proposal-store write failure preventing
command return; exact-content reconciliation; actual processed-only publication
before/after terminal cancellation; declined/unknown replay at capacity; mixed
UTF-8 byte limits; changed task context/peer key binding; and response operation
correlation rejection, foreign packet-header rejection, and the terminal
content-observation limitation.

Twenty-four candidate FacadeTests also pass independently. The separate candidate
SequentialDemoTests and unchanged baseline suite were not run by this reviewer.
Test results are in test-results.txt and candidate-unit-results.txt. File hashes
are in REVIEWED_SHA256.json. These are targeted application-contract checks,
not production acceptance or clearance of excluded review gates.
