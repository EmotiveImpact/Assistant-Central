# Encrypted local application payloads

This is a local pilot building block, not production security certification.
Use fictional data until independent security and deployment review is complete.

## Scope and format

New runtime databases use `assistant-central-application-storage/1`. The following
TEXT columns hold versioned encrypted envelopes, rather than application text:

- `runtime_items.body`: task and artifact content, titles and source permissions.
- `runtime_audit.data`: structured audit event details.
- `pilot_provider_runs.binding`, `request`, `review`, `result`.
- `pilot_workflow_artifacts.review`: the exact original result-to-draft mapping.

The SQLite transaction model is unchanged. Ciphertext is written before a commit,
so the journal contains ciphertext rather than a temporary plaintext payload.
No plaintext shadow table, file, disk-backed staging database or backup is made.
Routing metadata, public identities, IDs, digests, timestamps, state, counters,
provider response IDs and error labels remain visible. Existing peer packets are
already encrypted and are retained byte-for-byte. HTTP/mailbox files and other
subsystems are not re-encrypted. Opaque identifiers must not contain private text.

Each envelope uses a fresh ephemeral X25519 key and random 96-bit nonce, HKDF-SHA256
and AES-256-GCM. Associated data and the key derivation bind the format, local owner
fingerprint, table, primary key and column. The existing owner's exchange key opens
the envelope. No new password, master secret, recovery authority or credential is
created. Known-password maintenance rewraps that same immutable identity and does
not change any stored application ciphertext.

Sealing uses the public key so a single already-dispatched provider request can
retain its late response after owner logout. Opening requires the unlocked vault
and a non-expired local session. Normal owner APIs still verify the exact caller's
session and current task/source authority. This internal storage primitive is not
an additional owner, peer or network API. A late response never grants another
provider call or releases an artifact.

**Public-key sealing does not authenticate the writer.** Someone who can replace
the store and knows its public key can create new envelopes. AEAD detects damaged
or transplanted envelopes, but this format does not protect mutable consent/state
metadata against a malicious disk writer. Existing content/review commitments are
still checked. Do not treat the database as an independently verifiable consent
ledger. Complete database rollback, old row rollback, deletion, malicious same-UID
code, root, process memory, swap and host compromise remain outside this boundary.
A private OS account, disk encryption and external security review are still needed.

## Existing plaintext stores

An existing runtime without the exact format marker is refused before application
work. There is no automatic migration and no runtime plaintext compatibility flag.
A missing or altered marker, wrong identity, malformed/corrupt envelope or locked
vault never produces a plaintext fallback. Standalone provider unit fixtures have
an explicit `legacy_storage_fixture=True` choice; it is refused for a concrete
owner auth object or a database containing runtime metadata.

Stop the owner service first. With an existing, known-password local account:

    python -B -m pilot.storage_migrate --directory /private/owner

For the test/developer layout with separate auth/runtime directories:

    python -B -m pilot.storage_migrate --directory /private/owner/auth --runtime-directory /private/owner/runtime

The password is requested through a private terminal only. No command-line password,
echoed-stdin fallback, enrolment or identity generation is provided. Missing accounts,
wrong passwords, mismatched identities, foreign or permissive files, links, active
runtime connections, sidecars and unknown schemas are refused. The owner auth lease
and an exclusive runtime migration lease must both be available. Multiple normal
connections share the runtime lease and retain their existing SQLite serialisation.

Migration reads a bounded, descriptor-pinned original into an in-memory SQLite
database. It checks integrity, owner/version and recognised tables, refuses views
and triggers, encrypts known payload columns, performs a memory-only VACUUM, and
compares every logical row with its original. The original remains untouched until
the replacement is fully encrypted and verified. A new exclusive private
`runtime.sqlite.encrypted.pending` is written and fsynced, its bytes checked, the
source rechecked, then atomically replaces `runtime.sqlite`. The directory is fsynced
before reporting success. No peer packet, identity, acceptance, dispatch attempt,
original result, cancellation, audit sequence or workflow mapping is regenerated.

## Failure and recovery

- Before a pending output is created: a refusal leaves the original unchanged.
  Fix the exact cause and invoke migration explicitly when appropriate.
- If a pending output, SQLite journal/WAL/SHM or interrupted migration remains:
  stop and inspect. The command will not remove it, guess which copy is authoritative,
  repeat migration, restore a backup or create a new identity automatically.
- After a write/replacement/fsync failure: the result is uncertain. A restart may
  find the original plaintext store (still refused), an encrypted store, or a retained
  pending file. Inspect format, file ownership, integrity and retained original
  packets/results before any manual recovery. Do not repeat external sends or
  provider dispatch to test recovery. Losing an acknowledgement is not failure proof.
- A missing/corrupt vault or lost password is not recoverable by this command.
  Restore only a previously verified matching identity/store pair under an explicit
  recovery plan. Restoring old state can revive old decisions and must not be done
  casually; no anti-rollback authority is implemented.

Replacement is **not secure erasure**. Original blocks, deleted cells from old
copies, filesystem snapshots, crash dumps and backups may retain plaintext. Old
identity vault backups may still unlock encrypted records with their old password.
Never claim that migration, password changes or file deletion revokes those copies.

## Verification

`python -B -m unittest pilot.tests.test_storage -v` exercises all encrypted payload
columns, raw file checks, fresh ciphertext, context/owner substitution, corruption,
lock/unlock, late provider results, identity-preserving password changes, original
packets, explicit migration with exact logical state preservation, failure before
publication, uncertain file/directory fsync, retained pending refusal, links,
sidecars, wrong owner, unknown schema, expired sessions and transaction rollback.
The existing full pilot suite continues to test cancellation, replay, dispatch
uncertainty, workflow concurrency, restart and owner/peer boundaries.

The checks are synthetic and bounded. They are not cryptographic protocol review,
a power-loss filesystem proof, secret-memory erasure or hostile-host testing.
