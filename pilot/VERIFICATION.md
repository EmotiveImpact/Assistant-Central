# Synthetic pilot verification

Verified on 10 November 2026. Implementation commit:
`5c378d4ab6efb6bdb41114a1ee2875753ebaf488`.
Subsequent changes adding this record affect documentation only.

## Local regression evidence

| Command or component | Observed result |
| --- | --- |
| `python -B -m unittest discover -s pilot/tests -v` | 141 tests passed: 21 owner identity, 29 transport, 30 runtime, 27 provider and 34 independent review |
| `node --test pilot/web/tests/model.test.mjs` | 16 tests passed |
| `python -B pilot/web/tests/live_contract.py` | Actual HTTP state passed the frontend contract across two processes |
| `python -B -m pilot.demo` | Two processes/stores: accepted task, accepted return artifact, rejected alternative, cancellation observed with signed receipt, and both stores reopened after restart |
| `python -B tools/verify_import.py` | 673 imported files and 17 team manifest entries verified |
| `python -B team/run_checks.py` | 84 tests passed |
| `python -B execution/run_checks.py` | 133 tests passed |
| `python -B integration/run_checks.py` | 103 tests passed |
| `python -B prototypes/consent-v29/verify_checkpoint.py --full` | Overall passed: 948 Python tests and all 15 DOM checks, plus dependency/source verification |
| `python -I -B prototypes/synthetic-stdio-r5/run_all_checks.py` with an absolute script path | All 39 targeted checks passed |
| `git diff --check` | Passed |

Local Python was 3.12.14 with the pinned fixture dependencies, including
cryptography 50.0.0. Node was 24.22.1. Provider tests used synthetic fixture
transports. No live provider request or real credentials were needed.

## Actual browser evidence

The [`pilot-browser` job](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42736102322/job/129565612151)
passed on GitHub's Ubuntu runner, using Python 3.12.16, Playwright 1.62.1 and
Chromium 151.0.7922.34. It ran `pilot.ui_fixture` with fresh temporary encrypted
owner vaults and signed incoming proposals. The browser made real HTTP calls;
the live mode installs no mocked API routes.

Observed: authenticated sign-in, two exact review-digest-bound accept/reject
decisions, explicit exchange, activity history, public identity display, inert
content, no persistent browser token, mobile width without horizontal overflow,
logout clearing content and reload remaining locked. No page script errors were
observed. Desktop was 1440 by 1000; mobile viewport was 390 by 844.

The [desktop/mobile screenshot artifact](https://github.com/EmotiveImpact/Assistant-Central/actions/runs/42736102322/artifacts/13727021314)
contains two PNGs. Both were visually inspected after download. Actions artifacts
are subject to repository retention and this artifact initially expires on
8 February 2027; rerun the workflow to produce fresh evidence.

| File | SHA-256 |
| --- | --- |
| Downloaded ZIP | `019454e38d9e276b9d2326592369d720fc4d389ab91bf9744b476848d02bb285` |
| `assistant-central-desktop.png` | `17763a61483aa1584702a7c231ee89726c98712a5c2fbb80ad5e393a5e725690` |
| `assistant-central-mobile.png` | `3481ce35a9e5a579ac5c119d61fc5db3e70222f7225b2ab3e3223ec73b25d070` |

Local browser attempts were blocked by the managed environment before testing:
Chromium could not create its Unix socket and the cloud browser could not reach
the executor's loopback address. Those attempts do not count as passing evidence.

## Scope of the result

These results establish a synthetic local integration and automated browser
exercise. They do not establish independently controlled hosts, real-person
identity, live provider/account/billing acceptance, internet transport, forward
secrecy, an external security audit or production readiness. The frozen fixtures'
fictional owner approvals are not authenticated consent. Both pull requests remain
subject to explicit approval before merge.
