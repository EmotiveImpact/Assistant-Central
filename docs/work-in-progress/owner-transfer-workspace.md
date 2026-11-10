# Owner connection and transfer workspace

Coordination-only notice. Implementation owner: `/root/build_transfer_interface`, coordinated with `/root/advance_central_network`.

Base: main `fccc516e9192edd9c4a3ec3226d2acf153914c50`, including reviewed PR #8 and authenticated HTTPS adapter #13.

Scope: explicit owner controls for configured peer connections, retained outbox state and immutable HTTPS attempt inspection. Trusted host configuration chooses transport destinations and private quarantine roots; the browser cannot choose arbitrary file paths or CA files. Send, retry, selected import and cached receipt return remain separate authenticated owner operations. No background delivery, automatic consent, live credentials or deployment.

Owned paths: `pilot/server.py`, `pilot/web/`, new `pilot/owner_transfer.py`, focused transfer UI/server tests and documentation. Narrow CLI/test-helper changes may be needed. Do not edit auth/runtime/provider/workflow or signed grant/storage modules; coordinate any newly discovered overlaps.

Other active ownership inspected: #14 signed grant module, #15 application storage. Both are separate. Storage integration must use public packet helpers rather than raw plaintext rows.

Planned checks: strict request shape and CSRF/origin/session gates; redacted read-only status; immutable original packets; explicit retries and uncertain errors; selected quarantine path confinement; interruption, duplicate and offline flows; desktop/mobile browser interaction, relevant existing suites and exact-head CI. This initial commit contains no working implementation or completed verification.
