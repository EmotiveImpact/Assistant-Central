# Known-password owner maintenance

The first credential-lifecycle increment adds local password rotation without
changing the assistant's pinned identity or weakening peer or provider approval.
It deliberately leaves HTTP/UI integration to a later focused change; the active
reviewed-work-loop work owns those files.

## Scope

- `auth.py`: shared throttled password verification, fresh current-password check,
  new salt/nonce/vault wrapping, atomic revocation of all sessions and locked keys.
- `security.py`: offline terminal-only maintenance of an existing account. Requires
  the server to be stopped and refuses unsafe echoed-input fallback.
- `tests/test_password_rotation.py`: synthetic credential, race, persistence,
  failure-injection and CLI regressions.

Run `python -B -m unittest pilot.tests.test_password_rotation -v`. The existing
pilot test discovery automatically includes these checks. See [AUTH.md](AUTH.md)
for the command, exact guarantee and operational limits.

No live account, real password, provider call, remote transport or application
record deletion is introduced. A lost password remains unrecoverable; old vault
copies and compromised keys require a separately reviewed recovery/rotation plan.

## Verification

The implementation was tested on 10 November 2026 with Python 3.12.14 and the
repository's pinned cryptography 50.0.0 library. Final checks include 19 focused
password-maintenance tests (16 author tests and three independent review
regressions), the complete pilot suite, the real two-process exchange demo,
actual HTTP-to-interface contract and 16 interface model tests. Existing team
(84), execution (133), integration (103), 948-test consent checkpoint and all 15
DOM scripts, 39 targeted stdio checks, composition demo and import verification
also passed. The legacy consent run used the existing pinned offline dependency
directory for coincurve/bech32. No frozen fixture was edited.

Independent review reproduced an interrupted-commit gap: catching only ordinary
exceptions left an interrupted, rolled-back instance able to revive retained
session hashes after login. Credential transactions now fail closed for every
BaseException, preserve KeyboardInterrupt/SystemExit propagation, and require
restart before fresh login. Separate tests verify this repair, expiry after the
credential write, and unchanged queued ciphertext/pins across both owners'
password rotations. This is an internal engineering review, not an external
security audit. Hosted CI must be verified for the published commit separately.
