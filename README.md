# Assistant Central

A relationship-based network for people's personal assistants to coordinate
multidisciplinary work across providers, while each person retains control over
their work, information and commitments.

The goal is not a meeting scheduler or only a software-agent framework. A team
might coordinate research, copy, slides, websites, applications and repository
work. A nominated lead can coordinate parallel and dependent tasks, but cannot
approve another owner's actions or disclosure. See [the vision](VISION.md).

## Current state

This repository contains **synthetic local prototypes and a two-assistant pilot**.
No real model runs the examples and no provider account is connected. The pilot
exchanges encrypted peer messages over loopback between separate processes;
there is no production network, public publication, purchase or deployment.

| Component | Status | Evidence |
| --- | --- | --- |
| [Team coordinator](team/README.md) | New rebuilt local owner/task/artifact state machine | 84 tests, including 28 independent review tests |
| [Consent and protocol foundation](prototypes/consent-v29/README.md) | Recovered v29 prototype; executable source preserved | 948 Python tests and 273 DOM-model checks |
| [Synthetic stdio path](prototypes/synthetic-stdio-r5/README.md) | Recovered r5 launcher; executable source preserved | 39 targeted local stdio checks |
| [Team-to-protocol binding](integration/README.md) | Exact accepted artifact to unsigned local proposal; in-memory recovered wire path | 58 mapping and adversarial checks |
| [Recipient acceptance](integration/RECIPIENT_ACCEPTANCE.md) | Explicit synthetic release, per-source-owner controls and exact recipient accept/reject; restart and duplicate handling | 45 new checks; 103 total integration checks |
| [Two-assistant pilot](pilot/README.md) | Authenticated local owners, separate stores, encrypted delivery, exact decisions, provider adapter and browser workspace | Component/adversarial tests, actual two-process exchange and separate UI acceptance |
| [Reviewed work loop](pilot/WORKFLOW.md) | Opt-in synthetic request approval, original-result review and atomic return draft, followed by separate release/acceptance | Two-process HTTP, restart/offline delivery and independent authority regressions |
| [Execution ledger](execution/README.md) | One synthetic dispatch claim per started task; durable uncertainty and original-result recovery | 47 execution checks, including independent concurrency/cancellation review |
| [Provider disclosure gate](execution/PROVIDER_DISCLOSURE.md) | Exact synthetic destination and separate approvals from direct and upstream data owners; atomic one-shot local release | Provider and ancestry checks, including independent privacy, concurrency and withdrawal tests |
| [Integration readiness](docs/integration-readiness/README.md) | Native-host, identity, confidentiality and pilot gates | Design and static readiness evidence, not native acceptance |

The imported suites were rerun locally before the initial import. These are
separate proofs; their totals do not establish end-to-end interoperability. The
new binding tests cover only the local team-to-proposal boundary described below.
The execution ledger preserves uncertain attempts across restart without retrying
them; it does not invoke providers or grant authority to external tools. The new
provider disclosure rehearsal adds separate owner-specific data reviews and an
atomic local payload release, without making any live provider call.
The recipient acceptance extension separately rehearses accepting or rejecting
one exact artifact, without starting work or authenticating any human owner.
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

Agents starting new implementation work must open a draft PR before substantial
code changes, with scope, file ownership and verification plans. See [agent
coordination](AGENTS.md).

- `team/`: new team rebuild, tests, examples and provenance.
- `integration/`: exact team artifact mapping, synthetic in-memory wire demo and tests.
- `execution/`: synthetic dispatch ledger, crash/revocation checks and restart demo.
- `pilot/`: separate local assistants, authenticated owner controls, encrypted exchange, provider adapter and UI.
- `prototypes/consent-v29/`: recovered consent/protocol checkpoint with sanitized evidence paths.
- `prototypes/synthetic-stdio-r5/`: recovered synthetic stdio checkpoint with sanitized evidence paths.
- `docs/`: original architecture, security, pilot and integration-readiness material.
- `tools/verify_import.py`: checks the public import manifest and validates the team manifest.
- `.github/workflows/offline-checks.yml`: read-only-permission offline CI.

## Important boundaries

Owner labels and provider names are references, not authentication. The new team
API's owner methods are trusted local harness controls, not cryptographic approval.
Its bound agent facade is not an OS or Python sandbox. One local operator/database
still controls the fictional team.

The team layer now stages exact accepted artifacts through the recovered r5
proposal/wire building blocks in memory. It is **not connected to the v29 runtime,
the standalone r5 launcher or a peer transport**. Persistent human identity,
protected key custody, authenticated owner controls, distributed recipient
authority, native-host acceptance, live peer transport and safe wake behavior
remain separate integration work. Cancellation cannot recall content already read.

The new team source was rebuilt after the earlier local team commit became
unavailable. It does not claim to recover or reproduce that commit. See
[provenance](PROVENANCE.md). Product distribution and the license for original
project code remain undecided. Existing third-party licenses and notices are
preserved; see [license status](LICENSE_STATUS.md).

## Architecture research

See the [orchestration landscape and reuse plan](docs/research/orchestration-landscape.md)
for current framework, transport and licensing comparisons, and the
[roadmap](ROADMAP.md) for integration gates and a measured evaluation of Rust.
