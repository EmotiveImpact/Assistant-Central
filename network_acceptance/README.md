# HTTPS across distinct container networks

This is an independent **synthetic acceptance harness**, not a production
launcher. It places two fictional assistant owners and their ciphertext mailboxes
in **four different network, mount and PID namespaces** on an internal Docker
bridge. It exercises actual verified TLS 1.3 connections between containers, not
the existing shared-loopback network. It does **not** use two physical computers
or two independently controlled human accounts.

## Run

Use an already authorised Linux Docker engine and Python 3.12. Do not install an
engine, use `sudo`, disable security controls or publish ports just to run this
fixture. No Docker Compose or namespace administration is required.

```sh
python -m pip install -r pilot/requirements.txt
python -B -m unittest discover -s network_acceptance/tests -v
python -B -m network_acceptance.run --output /tmp/pilot-network-acceptance.json
```

The dedicated `Pilot HTTPS network acceptance` workflow runs both commands and
uploads a small success-only JSON report. A local guard-test pass is **not** a
container acceptance pass. The local TLS smoke intentionally substitutes Docker
controls; it cannot produce the acceptance report. A missing engine fails closed,
without a same-UID/loopback fallback or passing artifact. Record the exact tested
commit and hosted run before claiming container success.

## Topology and trust

Each owner uses a distinct non-root UID and private named owner volume. Every
container has a read-only root filesystem, dropped capabilities, private PID/IPC,
no-new-privileges, default seccomp and resource limits. Inspection checks the
actual process namespace IDs and effective protection state, not only requested
Docker flags. No host port, host bind mount or Docker socket enters a container.

Each mailbox mounts only its own quarantine and disposable TLS volumes. It has
**no owner authentication/runtime volume, owner password or session**. Its owner
mounts the matching quarantine read-only, and imports one explicitly selected
file. The peer's owner store, quarantine and TLS key are never mounted. TLS keys
are distinct per mailbox; each certificate has exactly its chosen DNS SAN. A
fresh two-hour test CA is generated for each run, its signing key stays in the
trusted controller's memory, and only its public certificate enters owner stores.
The test CA is not installed in host/system trust. No real credentials are used.

The test driver is trusted and has Docker authority. It provisions fictional
passwords, pins public identities, and performs explicit local owner operations
through `docker exec` stdin. Passwords and disposable TLS keys are not command
arguments, logs or evidence. These controls are **not** public owner endpoints,
real-person approval or a recommendation to expose Docker to an assistant.
Owner stores are closed after every operation. The helper is separate from the
product server and does not test the browser or #16's asynchronous transfer UI.
The synchronous public HTTPS adapter remains the exercised product boundary.

## What the actual-container run checks

1. Four genuinely distinct namespaces, expected UIDs/mounts/security profiles,
   internal bridge only, and no published host ports. A read-only readiness
   connection verifies negotiated TLS 1.3 and a non-loopback peer address.
2. Cross-owner passwords fail locally. The real persisted authentication delay is
   respected, never reset. Default system trust, a different CA and a resolvable
   hostname missing from the certificate all fail without quarantining bytes.
3. A valid TLS destination does not enrol an unknown sender. Quarantining bytes
   does not create an inbox item. Explicit sender selection is checked, and a
   tampered ciphertext copy may reach quarantine but cannot authenticate/import.
4. An ACK leaves the send journal uncertain. Separately importing the original
   signed receipt marks receipt only; the task is still pending/released until
   an explicit reviewed recipient decision. Duplicate import and receipt return
   preserve original receipt bytes. No receipt-for-receipt loop is created.
5. The accepted task supports a separately released return artifact to its
   original requester. Its arrival stays pending until separately accepted.
6. Stopping a real mailbox leaves a durable uncertain attempt. Restarting the
   sender retains its original packet digest and history. A plain resend is
   refused; one explicitly chosen retry after mailbox recovery sends the same
   original bytes and leaves recipient acceptance pending.
7. Local cancellation blocks further proposal sends without consuming an attempt.
   The recipient remains pending until the original signed cancellation is sent
   and explicitly imported. Duplicate proposal import cannot revive cancelled
   work, and an attempted later acceptance is refused.
8. Restarting both actual owner and mailbox containers retains exact owner
   identities, item state, audit records and immutable quarantine digests.
   Topology/security checks are rerun after restart. All quarantine entries are
   strict encrypted packets, and unique task/result/plaintext-password canaries
   are absent. No provider adapter store is created and no provider is called.

Every negative assertion requires the expected refusal/unknown-outcome class.
Unexpected I/O, schema or programming errors fail the run. The packet-tampering
probe deliberately uses a manual carrier copy to model an untrusted sender; it
is not a new owner-authorised send API and does not bypass product attempt gates.

## What this does not prove

All four containers share a host kernel and one trusted controller. A host/root/
Docker administrator, same-owner process compromise, kernel escape, dependency
compromise, malicious orchestration or snapshot rollback remains outside this
fixture. Two fictional password accounts are not two real people. A private
bridge with synthetic data is not Internet, NAT, firewall, DNS, certificate
renewal, two-physical-host or production deployment acceptance.

Ciphertext canary inspection is limited evidence that these known contents did
not appear in the mailbox, not a cryptographic audit or proof that metadata is
secret. Packet headers, IDs, lengths and timing are observable. This harness does
not claim runtime SQLite payload-at-rest confidentiality or anti-rollback
protection; see `pilot/STORAGE.md` when composing the storage work. It does not
prove file-level Unix permissions when volumes are absent; the existing
`isolation/` actual-volume adversarial checks cover that separate boundary.

Owner processes open and close stores for each explicit fixture operation. An
owner-container restart therefore verifies durable state reuse, not an abruptly
killed in-flight owner server or invalidation of a long-lived UI session. Mailbox
outage/restart is real. Mid-flight cancellation, dropped acknowledgements after
remote persistence, slow DNS, filesystem hangs and hard overall transport
deadlines remain separate adapter/UI tests and limitations. Cancellation cannot
recall bytes already copied, read or sent before the final gate. There is no
automatic retry, background import, acceptance, provider execution or external
agent communication.

The base image tag is mutable; this is not a signed/digest-pinned production
supply chain. Docker administrators can inspect stdin or memory; redacting test
logs does not defend against that administrator.

## Cleanup

A random `ac-https-*` prefix and `assistant-central.network-acceptance` label
identify one run's six private volumes, four containers, internal bridge and
image tag. Cleanup removes only those exact tracked/labeled resources, never
prunes unrelated resources. It runs on failure as well as success. If the engine
fails or the controller is killed, inspect the reported prefix/label and remove
only that run's resources. Interrupted volumes contain disposable synthetic
state and TLS keys and must not be reused. Evidence contains booleans/counts,
not passwords, sessions, keys, payloads or raw packet contents.
