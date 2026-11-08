# Assistant Central

A relationship-based network for people's personal assistants to coordinate
multidisciplinary work across providers, while each person retains control over
their work, information and commitments.

The goal is not a meeting scheduler or only a software-agent framework. A team
might coordinate research, copy, slides, websites, applications and repository
work. A nominated lead can coordinate parallel and dependent tasks, but cannot
approve another owner's actions or disclosure. See [the vision](VISION.md).

## Current state

This repository contains **offline fictional prototypes**, not a connected
production network. No real model runs the examples, no provider account is
connected, and no peer message, publication, purchase or deployment occurs.

| Component | Status | Evidence |
| --- | --- | --- |
| [Team coordinator](team/README.md) | New rebuilt local owner/task/artifact state machine | 84 tests, including 28 independent review tests |
| [Consent and protocol foundation](prototypes/consent-v29/README.md) | Recovered v29 prototype, preserved unchanged | 948 Python tests and 273 DOM-model checks |
| [Synthetic stdio path](prototypes/synthetic-stdio-r5/README.md) | Recovered r5 launcher, preserved unchanged | 39 targeted local stdio checks |
| [Integration readiness](docs/integration-readiness/README.md) | Native-host, identity, confidentiality and pilot gates | Design and static readiness evidence, not native acceptance |

These suites were rerun locally before this initial import. They are separate
proofs; their totals do not establish interoperability between the components.
GitHub Actions runs the same offline checks on pushes and pull requests. Check
the exact commit's Actions result rather than assuming a local pass means CI passed.

## Quick start

The new team layer requires only Python 3.11+ and the standard library:

```sh
python -B team/run_checks.py
python -B team/demo.py
```

The five-artifact demo explicitly simulates fictional owner approvals for
research, copy, a slide outline, a website draft and a PR draft. It creates no real
pull request. Artifact contents are inert text and have no tool authority.

For the recovered protocol experiments, read their own setup and limits before
running them. Full verification uses Linux, Python 3.12, Node 24 and the documented
pinned Python dependencies. The stdio suite intentionally excludes inherited
peer-lifecycle experiments and does not claim native-host acceptance.

## Repository layout

- `team/`: new team rebuild, tests, examples, provenance and preserved baseline ZIPs.
- `prototypes/consent-v29/`: exact recovered consent/protocol checkpoint.
- `prototypes/synthetic-stdio-r5/`: exact recovered synthetic stdio checkpoint.
- `docs/`: original architecture, security, pilot and integration-readiness material.
- `tools/verify_import.py`: checks published source against the original archive
  content and validates the preserved team manifest.
- `.github/workflows/offline-checks.yml`: read-only-permission offline CI.

## Important boundaries

Owner labels and provider names are references, not authentication. The new team
API's owner methods are trusted local harness controls, not cryptographic approval.
Its bound agent facade is not an OS or Python sandbox. One local operator/database
still controls the fictional team.

The team layer is **not yet wired to v29 or r5**. Persistent human identity,
protected key custody, authenticated owner controls, distributed recipient
authority, native-host acceptance, live peer transport and safe wake behavior
remain separate integration work. Cancellation cannot recall content already read.

The new team source was rebuilt after the earlier local team commit became
unavailable. It does not claim to recover or reproduce that commit. See
[provenance](PROVENANCE.md). Product distribution and the license for original
project code remain undecided. Existing third-party licenses and notices are
preserved; see [license status](LICENSE_STATUS.md).
