# Packaging notes

The builder's launcher, tests, runner, README, evidence and public fixture are unchanged from the independently reviewed candidate. `review/evidence/reviewed-inputs-before.json` and `reviewed-inputs-after.json` identify the reviewed hashes. The entire 128-file r4 baseline is copied byte-for-byte; no inherited test runner is invoked by this release's aggregate checks.

Independent tests were copied byte-identically into `independent_tests/`, as the reviewer specified. The report, summary, original review manifest and evidence were copied into `review/`. In the original `review/REVIEW_FILES.json`, paths beginning `independent_tests/` resolve from this release root; every other listed path resolves from `review/`. This is a placement map, not a source change. The independent bootstrap prefers its colocated release and has no original-workspace fallback.

The release coordinator added `START_HERE_R5.md`, this note, the aggregate `run_all_checks.py`, and release verification metadata. The coordinator's setup/rollback guide was included in the review's recorded inputs. The aggregate runner invokes only the 20 builder checks and 19 independent checks with isolated/no-bytecode Python flags. It does not call nested baseline runners, peer processes or key-generating demos.

`STDIO_SOURCE_MANIFEST.json` hashes all packaged files other than itself. It is an integrity inventory, not a cryptographic signature or permission to execute the release. The launcher's own startup check separately verifies the fixed r4 manifest and public fixture. A trusted, nonconcurrently modified source directory and trusted installed runtime are still required.

Historical nested reports describe their own earlier checkpoints, not present native-host acceptance. Repeated test runs do not increase the distinct count of 39 r5 checks. No native host/provider, installation, active configuration or excluded peer-process lifecycle review is part of this package validation.
