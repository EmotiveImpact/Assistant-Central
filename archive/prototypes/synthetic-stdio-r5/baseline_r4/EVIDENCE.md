# r4 candidate evidence

The new focused suite passed **32 tests** with bytecode disabled and
ResourceWarning elevated to error. See evidence/raw-checks.txt. The sequential
in-process full two-way demo also passed; see evidence/demo.json. Commands:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python run_raw_checks.py
PYTHONDONTWRITEBYTECODE=1 PYTHONWARNINGS=error::ResourceWarning python run_demo.py
```

Coverage includes duplicate and escaped-alias keys; strict UTF-8 and scalar
Unicode; finite numbers; pre-parser lexical depth; post-parser collection/node/
integer/depth/normalized-output constraints; raw and output byte cap boundaries;
batches/scalars; exact envelope/ID checks before SDK coercion; session-wide safe
ID consumption; malformed and ignored record budgets; fragment/coalescing/CRLF;
blank lines and undelimited EOF; lying readers and partial-return writers;
no retry after uncertain write; preserved accepted-output facts after reader
failure; output redaction; cancellation propagation and single use.

A real SDK ClientSession roundtrip also passes initialize, ping, tools/list,
propose, proposal_status and processed_inbox over independently encoded/decoded
client JSON/LF pumps. Request fragments are three bytes and response fragments
five bytes; multibyte emoji and escaped text survive. Client parsing uses standard
JSON plus SDK models, not the server codec.

Actual bytes pass through the real frozen r3 SDK bridge to unsigned proposal
persistence, exact-text replay and processed-only inbox. Escape-heavy valid
1024-byte NUL, quote, backslash and newline text and 1024-byte emoji text survive.
Tests verify endpoint state remains unchanged by proposal creation and that only
explicit synthetic-owner processing/publication exposes inbox content. A writer
failure after proposal admission leaves one local proposal persisted and records
uncertain output without retry.

No new dependency was installed. This candidate's focused run does not rerun or
replace frozen r3's 124-test evidence. The original complete r3 is copied into
baseline_r3 for independent preservation checks and existing check commands.
There is no source freeze, archive or upload for r4 yet. No process-lifecycle
review, native-host/stdio/network integration, human authentication, SDK logging
isolation or A4A interoperability claim follows from these tests.
