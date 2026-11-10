# Local owner authentication and key custody

`LocalOwnerAuth` provides a password-authenticated local account for exactly one
owner and one assistant in a private directory. It replaces caller-supplied owner
labels as runtime authority. It does not verify a real person's civil identity or
prove that two processes are controlled by different humans.

The root CLI must provision accounts through an interactive secret prompt and
must never place passwords in command arguments, logs or shell history. Bootstrap
is a trusted one-time control and must not be exposed as an unauthenticated HTTP
route. The server receives tokens through its authenticated channel, not through
owner IDs in request bodies.

## Interface

```python
auth = LocalOwnerAuth(private_directory)
auth.bootstrap(owner_id, agent_id, password)  # one-time trusted provisioning
token = auth.login(password, ttl=900)
identity = auth.authenticate(token)
public = auth.public_identity()
signature = auth.sign(token, bounded_bytes)
shared_secret = auth.exchange(token, peer_x25519_public_bytes)
auth.logout(token)
auth.close()
```

`authenticate` returns only `owner_id`, `agent_id`, `identity_fingerprint` and
`expires_at`. It accepts no owner or agent selector. `public_identity` returns
exactly `owner_id`, `agent_id`, `signing_key` and `exchange_key`; public keys use
canonical unpadded base64url. Metadata is detached from internal state.

`sign` and `exchange` require a valid current session and an unlocked vault. No
private-key export operation exists. Returned X25519 shared bytes are for the
transport's KDF, not direct use as encryption keys. The transport must pin the
full enrolled peer descriptor; a key supplied by an untrusted message is not
peer enrollment.

## Local credentials and storage

- Passwords require at least 12 characters and at most 1,024 UTF-8 bytes. They are
  processed by scrypt with an independently random 16-byte salt, N=32768, r=8,
  p=1 and a 64-byte result. The two halves serve separate verifier/encryption roles.
- A domain-separated HMAC verifier binds the password to the complete public
  descriptor. AES-256-GCM encrypts the 64-byte Ed25519/X25519 private-key material
  with a random 12-byte nonce; the descriptor and version are authenticated data.
- The account directory must be owned by the running UID with mode 0700. The
  SQLite database and lock file must have mode 0600, the same owner, no symlink
  and one hard link. Existing permissive paths are rejected without changing
  their permissions. Inode substitution is rejected while the process runs.
- An exclusive POSIX file lock permits one owner-authentication process per
  account directory. SQLite uses `synchronous=FULL`. Database contents contain
  a verifier and encrypted key material, never a raw password or private key.
- Login failures have persisted exponential cooldowns, starting at one second
  and capped at thirty seconds. A successful login clears the failure count.
  This limits online attempts but cannot prevent local denial of service or
  offline attacks against a stolen encrypted database.

Sessions are 32 random bytes encoded as opaque bearer tokens. Only a
domain-separated SHA-256 digest is stored. Each session has a finite lifetime
between one second and one hour, with at most 32 concurrent active sessions.
Logout deletes that token; `revoke_all(token)` requires a current session and
revokes every session. The last logout drops the unlocked key references.

Restart and `lock()` invalidate all sessions and require the password again.
Expiry prevents authentication, signing and decryption. A backwards or invalid
process clock fails closed. Status distinguishes local password authentication
from human identity verification and contains no token, password or private key.

## Transaction ordering

Runtime/provider decisions must hold the authentication guard across their own
database transaction:

```python
with auth.authorised(token) as identity:
    with runtime_transaction():
        # Check exact owner, artifact, peer, permissions and request context.
        # Write the durable decision/fence and its audit record.
        auth.authenticate(token)  # final TTL check immediately before commit
```

`authorised` holds a reentrant process lock. Logout, lock and revocation cannot
commit between the final session check and the runtime commit. The runtime
transaction must be nested inside the guard, and external I/O must occur after
the durable fence and after leaving both transactions. Authentication alone does
not authorise artifact disclosure, provider dispatch, peer enrollment or spending.

## Explicit limits

This is a POSIX local-account implementation. The process must run under its
owner's separate OS account to establish ownership against another local user.
Two directories under the same UID demonstrate separate application state, not
OS isolation. Permissions and password encryption do not protect against root,
malicious code in the process, a compromised owner host or an attacker with the
same UID. Python does not guarantee zeroisation of password/key bytes in memory.

There is no unattended unlock, external identity provider, multi-factor login,
hardware keystore, automatic key rotation, password reset or encrypted backup
recovery. A lost password means the encrypted identity cannot be recovered by
this implementation. Restoring an older database can restore older metadata;
backup rollback protection is not claimed. Replacing an identity requires a new
local account and explicit peer re-enrollment, never silent key substitution.

The authentication tests exercise synthetic accounts only. Independent deployed
two-person ownership, compromised-host recovery and production key custody remain
separate operational acceptance work.

Cryptographic APIs follow the official documentation for
[AES-GCM](https://cryptography.io/en/stable/hazmat/primitives/aead/),
[X25519](https://cryptography.io/en/stable/hazmat/primitives/asymmetric/x25519/)
and [Ed25519](https://cryptography.io/en/stable/hazmat/primitives/asymmetric/ed25519/).
The repository pins cryptography 50.0.0 for this tested environment.
