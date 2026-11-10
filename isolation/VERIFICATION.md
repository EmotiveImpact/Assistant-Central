# Container-isolation verification record

## Original PR #7 baseline

Implementation commit: `23c62f45940972cfeafae6888b7d8b0f6ac2b6d2`.
The original evidence commit added this record, three harness regression tests,
and removed the redundant feature-branch push trigger. The baseline below
predates PR #8's reviewed-work-loop and address-reuse changes.

## Actual Docker integration

- [Successful GitHub run, 10 November 2026](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42782424364)
- [Container-isolation job](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42782424364/job/129715409812)
- Artifact: `pilot-isolation-evidence`, ID `13746267368`, created 08:26:20 UTC.
- Artifact ZIP SHA-256:
  `b41ce785833cc8ee90c3f80f38d1f56784e78a439b1ba7a3f2e9f35a6474335f`.
- GitHub-hosted Ubuntu Linux; host Python 3.12.16, official
  `python:3.12-slim-bookworm` container image, pinned `cryptography==50.0.0`.
- Exact command: `python -B -m isolation.run --output "$RUNNER_TEMP/pilot-isolation.json"`.

The actual job, not a mock, returned `result: passed` after cleanup:

- Nonroot UID/GID 21001 and 21002, distinct cryptographic fingerprints, private
  owner volumes and separate mount/PID namespaces.
- 32 denied filesystem/code operations from Atlas toward Beacon and 32 in the
  reverse direction under the deployment mounts.
- Another 32 denials in each direction with both actual writable owner volumes
  mounted into separate nonroot DAC diagnostic containers: **128 denials total**.
- All victim file hashes, modes and ownership unchanged.
- Other-owner passwords and sessions rejected both directions.
- Synchronization did not deliver an unreleased task or artifact.
- Reviewed task and return artifact exchanged and explicitly accepted through
  the existing pilot HTTP routes; receipt alone did not become acceptance.
- After actual container restart: exact item IDs/digests/decisions, reviewed
  content and audit history preserved; old sessions rejected; public identities
  unchanged. Provider activation remained disabled.

## Supporting checks and fixes

- Existing pilot tests: **141 passed locally**, unchanged implementation.
- Harness guard suite: **19 passed locally** after adding port-expiry/restart
  regression checks (16 existed in the integration run cited above).
- Independent review found and corrected two possible false positives: checking
  an unreleased draft without synchronizing, and allowing a DAC probe to pass on
  an unmounted placeholder. Both are now explicitly exercised/verified.
- The first real build exposed ambiguous uncompressed PAX archive detection in
  Docker stdin handling. The context is now gzip-compressed and self-tested.
- Real same-port restart exposed the existing pilot's `allow_reuse_address=False`
  behavior. A local reproduction returned EADDRINUSE after HTTP traffic. The
  harness now stops both servers, waits for normal socket expiry, then restarts.
  No authentication/runtime/provider/server/UI code, capabilities or host sysctls
  were changed to obtain the passing result.

## Composition with PR #8 and PR #9

The harness now integrates PR #9 at `54b8ce69689746516512fd3ba79ed51f805d8408`,
which includes the merged PR #8 implementation. PR #8 deliberately enables
`SO_REUSEADDR` to reopen a pinned endpoint after restart; its own tests reject
sharing an active listener. The harness's port probe now matches that reviewed
option and verifies both active endpoints cannot be rebound before stopping
them. It never uses `SO_REUSEPORT` or changes host settings. A bounded 15-second
availability check replaces the historical 90-second socket-expiry wait.

The guard suite adds a regression that rejects an unexpectedly rebindable live
listener. The cumulative Docker, pilot, workflow, password-maintenance and full
CI results are linked from the PR description; older results above establish
only the explicitly identified earlier baseline.

The editor machine had no Docker CLI and correctly failed closed. No local
same-UID test is represented as container-isolation evidence. See [README.md](README.md)
for the precise attacker model, shared-loopback limitation and untested host/kernel,
real-person, provider, recovery and production-deployment boundaries.
