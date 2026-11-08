# Public import verification

Fresh local checks on Linux/Python 3.12 and Node 24, November 8, 2026:

| Check | Result |
| --- | --- |
| Team coordinator | 84 tests passed, including 28 independent review tests |
| Consent/protocol v29 | 948 Python tests passed |
| v29 frontend models | All 15 DOM suites passed, 273 checks |
| v29 source integrity | 153 source hashes and 13 vendored-file hashes passed |
| Synthetic stdio r5 | 39 targeted local checks passed |
| Team demonstration | Fictional five-artifact run completed |
| Public import integrity | 673 imported files and 17 team-manifest entries verified |
| Source preservation | 215 runtime/test/UI files match recovered input bytes |

The suites are separate. They do not prove the team layer interoperates with v29
or r5. No native host, real provider account, real owner credentials or production
transport was exercised. Inherited r4 peer-lifecycle experiments were not rerun
or included in the r5 result.

Source integrity checks establish consistency, not authenticity or security.
Historical logs remain historical, including earlier failing intermediate runs.
The publication cleanup affects metadata and historical evidence paths, not
runtime source. See [provenance](../PROVENANCE.md).

## Browser screenshots

The v29 local application started successfully, but the available cloud browser
could not reach the execution environment's loopback address. No screenshots
were captured and no mockups were substituted. DOM-model checks are not browser,
visual or accessibility acceptance. Screenshots can be added after an authorized
browser can reach a running fictional fixture.

## Reproduce

Install the pinned dependencies in a dedicated virtual environment using the
prototype setup instructions, then run:

```sh
python -B tools/verify_import.py
python -B team/run_checks.py
python -B team/demo.py
python -B prototypes/consent-v29/verify_checkpoint.py --full
python -I -B "$PWD/prototypes/synthetic-stdio-r5/run_all_checks.py"
```

`IMPORT_MANIFEST.json` records the initial imported files, rather than all future
project files. Deliberate changes to imported files require reviewing and updating
their recorded digests. Do not silently update a failed integrity check.

GitHub Actions runs these offline checks separately. A local pass is not a CI pass;
inspect the Actions result for the exact commit.
