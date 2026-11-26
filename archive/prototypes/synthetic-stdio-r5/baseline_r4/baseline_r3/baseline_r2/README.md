# Independent-peer experiment

**Synthetic, offline architectural experiment. Not a live network, production
security certification, A4A-compatible implementation, or native-host integration.**

This separate prototype addresses the v29 shared-application-authority gap. Alice
and Bob run in different child processes with different SQLite stores. Each child
generates and retains only its own private identity keys. Each recipient validates
its own live authorization and request linkage instead of relying on the sender's
outbox. The trusted fixture simulates explicit owner decisions for both sides.

Nothing here modifies or imports the frozen main prototype or any v3–v29 ZIP.
There are no accounts, enrollment, real credentials, installations, sockets,
listeners, external messages, relays, browser actions, or publication.

## Run

Tested with Python 3.12.14 and the already available cryptography 50.0.0. No
installation is needed in the provided environment. The only non-stdlib runtime
dependency is cryptography; `requirements-experiment.txt` records the tested pin,
not an instruction to install software.

From this directory:

```sh
PYTHONDONTWRITEBYTECODE=1 python run_checks.py
PYTHONDONTWRITEBYTECODE=1 python -m independent_peer.demo
```

The aggregate command checks the frozen source manifest, runs the targeted test
suite, and executes the synthetic demo. Individual tests can also be run with:

```sh
PYTHONDONTWRITEBYTECODE=1 python -m unittest discover -s tests -v
```

The demo prints separate endpoint PIDs, confirms receipt is not processing, and
shows Alice processing a fictional result. Keys and databases are generated only
inside disposable runs. Normal fixture exit deletes the databases and reaps the
children. Failure also triggers cleanup, with uncertainty reported if cleanup
cannot be confirmed. There is no persistent-key recovery or retained-run recovery.

## Layout

- `independent_peer/protocol.py`: strict grammar, standard cryptographic primitives,
  and a new experimental envelope.
- `independent_peer/endpoint.py`: one endpoint's SQLite policy, inbox, outbox,
  operation journal, and processed-only projection.
- `independent_peer/pipes.py`: two inherited fixed pipe lanes with bounded framing.
- `independent_peer/worker.py`: ordinary endpoint process entry point.
- `independent_peer/fixture.py`: trusted local supervisor and public bootstrap.
- `independent_peer/demo.py`: fictional request/result exercise.
- `tests/`: targeted state, malicious-sender, transaction, framing and lifecycle tests.
- `docs/DESIGN.md`: trust model, exact state semantics, limits and invariants.
- `docs/EVIDENCE.md`: evidence map and commands, including known non-goals.
- `docs/INDEPENDENT_REVIEW.md`: independent adversarial findings and fixes.
- `SOURCE_MANIFEST.json`: exact allowlist and hashes for the frozen source/docs/tests.
- `evidence/`: test-run output, not keys, databases or runnable runtime state.

The malicious and post-commit fault workers are **test-only** modules selected by
trusted test startup. Peer bytes cannot select a worker, import a module, invoke a
signing oracle, or access owner methods on an ordinary endpoint.

## What this proves, narrowly

A separately running recipient can reject a cryptographically valid but
unsolicited, stale-consent, misbound, out-of-order or oversized message using its
own state. A signed persistence receipt does not create a processed projection.
The sender records processing only from exactly bound recipient-signed evidence.
Exact replay creates no duplicate application transition.

A malicious endpoint can still lie about its own processing with its own key.
Signed evidence is an authenticated endpoint claim, not proof of honest human,
model, or external-world behavior. Same-user processes are not OS isolation. The
supervisor controls both fictional owner pipes and does not represent two real,
independently authenticated people. Independent adversarial review and ten additional process probes are included.
The combined 55-test suite remains targeted evidence, not production acceptance.
