# Disposable two-assistant isolation harness

This harness runs the **existing** `pilot.server` twice as separate non-root Unix
users in separate Linux containers. It changes no pilot authentication, runtime,
transport, provider, or UI code. All owners, tasks, passwords and artifacts are
synthetic. It never calls a model provider or publishes a listening host port.

## Run

Use a checkout containing this harness and the reviewed-work-loop pilot (PR #8 or later),
Python 3.12 on the host, and an **already authorized Linux Docker engine** with
seccomp enabled. Docker Desktop's Linux engine or rootless Docker may work, but
the recorded CI target is the standard GitHub-hosted Ubuntu Docker engine.
Windows containers are unsupported. Registry access is needed to build the
official Python image and install `pilot/requirements.txt` from PyPI.

```sh
# Fast, dependency-free harness self-tests. These do not verify isolation.
python -B -m unittest discover -s isolation/tests -v

# Real container / cross-UID / HTTP tests. Use a fresh output path.
python -B -m isolation.run --output /tmp/pilot-isolation-result.json
```

The second command takes a few minutes on a cold image cache. It fails with a
nonzero exit if Docker, the daemon, registry, seccomp, an assertion, or cleanup
is unavailable. There is **no same-UID fallback and no skipped-test success**.
The harness does not install Docker, invoke sudo, create host users, configure
daemon access, change host security settings or request privileged containers.
If you lack access to an authorized Docker engine, use the **Pilot container
isolation** GitHub Actions job instead. Docker daemon access itself is powerful;
do not grant it to an assistant or untrusted workload just to run this test.

A successful command prints JSON and optionally writes the same credential-free
report. Credentials travel only via trusted controller memory and stdin, never
command arguments, environment variables, build contexts or the report. Do not
enable shell tracing, print subprocess input or retain debug memory dumps.
The report is written only after tests and disposable-resource cleanup succeed.
The CLI refuses an existing output file, so an older success cannot silently be
mistaken for a new failed run.

## Topology and claims

- `atlas`: UID/GID 21001, only its `/private/atlas` named volume mounted.
- `beacon`: UID/GID 21002, only its `/private/beacon` named volume mounted.
- Each server has its own PID/mount/IPC namespace. Private directories are 0700;
  the existing pilot creates its vault and databases with its existing modes.
- All containers run non-root, with all Linux capabilities dropped,
  `no-new-privileges`, default seccomp, a read-only root filesystem, bounded
  memory/CPU/processes and a small private no-exec temporary filesystem.
- A dedicated `--network none` anchor supplies a **shared loopback network
  namespace**. Only `lo` may exist. Neither a bridge/host network nor host port
  publishing is used. This deliberately preserves the pilot's loopback-only
  endpoint validation and unmodified transport. It is **not network isolation
  between assistants**, a remote carrier, or independent-host deployment.
- A trusted controller with no owner volume joins this same loopback namespace
  to perform synthetic owner HTTP actions. Like an operator holding both test
  passwords, it is outside the attacker model. The Docker host/controller and
  image build are also trusted.

The build sends only allowlisted, versioned pilot source and explicit test helper
files, not the entire checkout, `.git`, untracked files or owner data. No runtime
container receives host bind mounts, a Docker socket or provider credentials.
The other owner's password/token is supplied only in the deliberate synthetic
cross-owner authentication rejection probes, never for normal operation.
The helper module is test tooling, not a new
owner API or a production deployment recommendation.

## What the integration check actually verifies

1. Distinct expected numeric UIDs/GIDs and cryptographic fingerprints, independent
   private volumes, actual process namespace IDs, effective/permitted capability
   sets, seccomp and `no-new-privileges`. Inspect assertions reject shared private
   mounts, host networking, published ports and shared PID/IPC configuration.
2. Both owners can create/read/update/delete a positive-control file in their own
   store. In **both directions**, a process running as the attacking owner tries
   to enumerate, read, overwrite, unlink, chmod and rename known peer files,
   inject/replace a file, access a peer canary through a symlink, change the peer
   directory's permissions and overwrite the shared application code. Unexpected
   errors (for example I/O failure or disk exhaustion) do not count as isolation.
3. A separate diagnostic container for each attacker deliberately mounts **both
   actual writable owner volumes**. The trusted host verifies the mount names and
   destinations, then repeats the probes as the attacker's non-root UID. This
   prevents an absent peer mount or a read-only mount from masquerading as a Unix
   permission test. Direct access must yield EACCES/EPERM. Cross-volume replacement
   may additionally yield EXDEV. These diagnostic containers are not pilot server
   containers and are removed immediately; do not deploy this double-mount setup.
4. Hashes, ownership and permissions for every victim file, including its real
   identity vault, SQLite stores and synthetic canary, are identical before and
   after all attack probes. No hash or secret file content is printed in evidence.
5. The unchanged owner HTTP routes reject the other owner's valid password and
   session. Public identities are explicitly fingerprint-pinned in both directions.
   Synchronization before release does not deliver either a task or its artifact.
   After reviewed release, the task crosses the HTTP boundary, remains pending
   until recipient acceptance, and an independently released return artifact is
   accepted by the original requester. A transport receipt is not owner acceptance.
6. Restarting both actual server containers preserves each identity and the two
   accepted items, exact reviewed content and audit history on its own volume
   while invalidating old owner sessions. The pilot enables `SO_REUSEADDR` so its
   pinned endpoints can reopen after restart despite old `TIME_WAIT` connections.
   The harness uses the same option and first verifies that neither live listener
   can be rebound. It then stops both servers and allows up to 15 seconds for the
   endpoints to become available before restarting them. It never sets
   `SO_REUSEPORT`, changes host sysctls or weakens container protections. Live
   provider activation remains disabled throughout.

The fast unit tests mutate guard inputs to ensure unsafe settings are rejected,
check the build allowlist and error redaction, and ensure a successful operation
or an unrelated failure cannot be counted as a denied attack. They do not replace
the real Docker test.

## Threat model and limitations

The attacker can run arbitrary code as one assistant's unprivileged container UID,
read and destroy **its own** data, and contact the peer's loopback HTTP listener.
It cannot control the Docker daemon/host, controller, images, kernel, other
owner's credentials or deployment configuration. This harness adds measured
mount/PID/Unix-permission boundaries beyond the same-UID demo. It is not a sandbox
escape assessment, formal proof, audit or security certification.

Containers share a host kernel. Kernel/engine bugs, root/daemon administrators,
compromised builds/dependencies and orchestration credentials can defeat these
boundaries. Distinct container UIDs are not proof of independently controlled
human accounts or devices. Rootless/user-namespace mappings, SELinux/AppArmor,
alternate engines and OS versions require their own runs; do not disable their
protections just to make this fixture pass. The Python base tag is mutable and
the image is not a signed, digest-pinned production supply-chain artifact.

Private directories and mounts do not encrypt the runtime SQLite store. A host
administrator, backup reader or attacker with the owner's credentials can still
access private plaintext. Recovery, retention/deletion, storage encryption,
backup rollback, identity rotation, real-person enrolment and remote transport
remain separate work. The shared network allows peer listener probing and
resource-exhaustion attempts; this test neither proves denial-of-service
resilience nor exhaustively tests HTTP authorization or packet cryptography.
The existing pilot test suites remain required. No real provider or personal
data handling, malicious model output, billing, or live spending is tested.

## Cleanup and evidence

Each run uses random `ac-isolation-*` names and the
`assistant-central.isolation` label. Only its own containers, volumes and image
tag are removed in `finally`; unrelated resources are never pruned. If a crash or
engine outage interrupts cleanup, inspect the exact resource names in the error
and the label before manually removing them. Do not use global prune commands.
Runtime passwords/tokens are not persisted, but interrupted volumes contain
synthetic private state and should not be reused.

The separate `.github/workflows/pilot-isolation.yml` job runs unit and actual
container checks and uploads `pilot-isolation-evidence` only on success. Existing
CI files are untouched. Its run URL and commit SHA establish which revision was
tested; a green self-test alone is never reported as a container-isolation pass.
