# Two-assistant local pilot

This pilot implements two separate running assistants with password-authenticated
owner controls, private stores, protected signing/encryption keys, pinned peers,
encrypted packets, durable decisions and a responsive browser workspace. It also
includes a concrete OpenAI Responses adapter whose live activation is disabled.

All examples, tests and fixtures use fictional people and text. No real provider
call, public deployment or actual two-person enrolment was performed. Separate
processes under one OS user prove API/process separation, not protection against
that user reading both stores. The server listens only on `127.0.0.1`.

## Run the complete disposable exchange

Use Python 3.12 on Linux/macOS with the pinned dependency in a private environment:

```sh
python -m venv .venv-pilot
.venv-pilot/bin/python -m pip install -r pilot/requirements.txt
.venv-pilot/bin/python -B -m pilot.demo
```

The demo generates fresh temporary identities/passwords, starts two actual HTTP
processes, pins each peer, sends a reviewed task, records recipient acceptance,
returns an artifact only to its original task owner, records artifact acceptance,
rejects an alternative and propagates cancellation. It restarts both processes
and verifies retained history. Credentials and private keys are never printed or
included in evidence. No model authors the fictional artifact in this demo.

## Run two owner workspaces

Provision each local account through a terminal. Passwords are entered privately
with `getpass`, never via arguments or configuration files. Use private owner
directories; existing directories with permissive modes are refused.

```sh
python -B -m pilot.server init --directory /private/path/owner-a --owner owner-a --agent atlas
python -B -m pilot.server init --directory /private/path/owner-b --owner owner-b --agent beacon
python -B -m pilot.server serve --directory /private/path/owner-a --port 8765
# In a separate terminal:
python -B -m pilot.server serve --directory /private/path/owner-b --port 8766
```

Open the two displayed loopback addresses in separate browser windows. Sign in,
open **Trusted peers**, exchange the public identity descriptors, independently
compare the complete fingerprints and explicitly enrol each exact peer with the
other local address. Keys supplied by a packet are never automatically trusted.

Create a fictional task, open its exact review and approve release. Use **Sync
exchange** in each workspace to transfer/ingest queued packets while signed in.
The recipient reviews and accepts or rejects the task. An accepted task can
receive an artifact reply only along its signed origin-return route. Review and
release that artifact, synchronise, then review the result at the original owner.
**Activity** records decisions. Logout and restart lock key access; no unattended
background unlock is provided.

The browser retains bearer sessions only in memory and renders artifact content
as inert text. Uncertain mutations require status inspection. A local owner
session is not an external identity check or proof that a particular real human
reviewed the content.

## Implemented boundaries and remaining limits

| Component | Implemented | Remaining limit |
| --- | --- | --- |
| [Owner controls](AUTH.md) | Scrypt passwords, encrypted identity vault, expiring hashed sessions, throttling, logout/restart lock | No MFA, external identity proof, hardware custody or reviewed rotation/recovery |
| [Runtime](RUNTIME.md) | Separate stores; every owner decision requires the local session | Same-UID/root compromise and separately owned deployment unverified |
| [Exchange](TRANSPORT.md) | Pinned Ed25519/X25519 identities, AEAD packets, bounded original retries, durable dedup/receipts | Loopback carrier only; no internet service, forward secrecy or backup rollback claim |
| [Provider](PROVIDER.md) | Concrete Responses request, signed source grant plus recipient approval, bounded one-shot dispatch | Disabled by default; live account, billing/data policy and response acceptance unverified |
| [Interface](INTERFACE.md) | Sign-in, peer enrolment, reviews, acceptance/rejection, release, withdrawal, sync/history | Synthetic automated acceptance, not an actual two-person trial |

The old shared-team `BoundArtifactProposal` and `AcceptanceBoundary` remain
separate fixtures. Their fictional decisions are not upgraded into authenticated
grants. This pilot requires fresh authenticated review and signed peer contracts.
It supports direct owner-originated task declarations and exact artifact returns
to the original owner. General inherited-source forwarding is rejected until
independently verifiable upstream permissions have a reviewed contract.

Cancellation requested locally, authenticated remote observation and historical
acceptance are distinct facts. An unexpired proposal may be accepted before a
delayed cancellation arrives. A receipt cannot prove execution, remote shutdown
or recall of exposed text. Uncertain provider requests are never retried.

## Verification

```sh
python -B -m unittest discover -s pilot/tests -v
python -B -m pilot.demo
node --test pilot/web/tests/model.test.mjs
python -B pilot/web/tests/live_contract.py
```

The [verification record](VERIFICATION.md) identifies the tested code, commands
and hosted browser evidence. The [independent agent review](SECURITY_REVIEW.md)
records concrete findings/fixes;
it is not third-party security certification. CI runs existing regressions plus a
real Chromium check against `pilot.ui_fixture`, with desktop/mobile screenshots
saved as an Actions artifact. That fixture has a public test-only password and
must never be reused for a real account.

The next externally verified milestone needs two actual owners on separately
controlled OS accounts/devices, a reviewed remote carrier and a named provider
account with explicit account/data-policy/billing approval. Identity recovery,
retention/deletion, backups, incident handling and live cancellation expectations
remain acceptance work before introducing personal data.
