# Recorded commands and results

Working directory for these commands was `/path/to/workspace`, except the relocation subprocess explicitly used a temporary unrelated directory. Python resolved to `python3.12`.

## Final builder checks

```
python3.12 -I -B agent-network-synthetic-stdio-r5/run_checks.py > agent-network-stdio-review-r5/evidence/builder-checks-final.stdout.log 2> agent-network-stdio-review-r5/evidence/builder-checks-final.stderr.log
```

Exit 0. **20 tests passed in 9.007 seconds.** This is the final `4df94f7f...529571` launcher. The earlier `builder-checks.*` logs are an interim independent rerun before the builder's final small reader/stderr corrections; they are not used as the final-build proof.

## Independent checks

```
STDIO_R5_ROOT="$PWD/agent-network-synthetic-stdio-r5" python3.12 -I -B agent-network-stdio-review-r5/independent_tests/run_checks.py > agent-network-stdio-review-r5/evidence/independent-checks.stdout.log 2> agent-network-stdio-review-r5/evidence/independent-checks.stderr.log
```

Exit 0. **19 tests passed in 9.058 seconds.** All final source hashes are in `reviewed-inputs-before.json` and `reviewed-inputs-after.json`.

## Relocation/bootstrap check

The following exact Python command copied the release into a temporary directory, placed the independent tests in the intended release layout, deliberately supplied an invalid environment override and launched from an unrelated directory:

```
python3.12 -I -B - <<'PY'
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile
source=Path('agent-network-synthetic-stdio-r5').resolve()
review=Path('agent-network-stdio-review-r5').resolve()
with tempfile.TemporaryDirectory(prefix='r5-review-relocation-') as temporary:
    base=Path(temporary)
    relocated=base/'relocated-release'
    shutil.copytree(source,relocated)
    shutil.copytree(review/'independent_tests',relocated/'independent_tests')
    unrelated=base/'unrelated-cwd'
    unrelated.mkdir()
    command=[sys.executable,'-I','-B',str(relocated/'independent_tests'/'run_checks.py')]
    environment=dict(os.environ,STDIO_R5_ROOT=str(base/'must-not-be-selected'))
    result=subprocess.run(command,cwd=unrelated,env=environment,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=90)
    (review/'evidence'/'relocated-checks.stdout.log').write_bytes(result.stdout)
    (review/'evidence'/'relocated-checks.stderr.log').write_bytes(result.stderr)
    record={'command':command,'cwd':str(unrelated),'STDIO_R5_ROOT':environment['STDIO_R5_ROOT'],'returncode':result.returncode,'launcher_sha256':hashlib.sha256((relocated/'launcher.py').read_bytes()).hexdigest(),'claim':'Colocated release wins over invalid explicit environment path; tests loaded by exact colocated file, with unrelated working directory.'}
    (review/'evidence'/'relocated-result.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))
    print(result.stderr.decode())
    raise SystemExit(result.returncode)
PY
```

Exit 0. **19 tests passed in 7.550 seconds.** `relocated-result.json` records the exact temporary command/path, selected invalid override, final launcher hash and return code. This is a repetition of the independent 19, not 19 additional tests.

## Source/preservation evidence

`reviewed-inputs-before.json` records the selected source root, Python/dependency versions and SHA-256 of 12 reviewed files. `reviewed-inputs-after.json` repeats those hashes and records exact equality and no generated `.pyc` files.

`preservation-check.json` compares opaque complete-tree SHA-256 mappings against the candidate's preimplementation `evidence/preserved-inputs-before.json`: candidate baseline 128/128 unchanged, original r4 128/128 unchanged, original preparation 8/8 unchanged. No inherited executable test suite was used for these comparisons.

Unittest intentionally writes its report to stderr. The check runner's stdout logs are empty; this does not describe launcher failure diagnostics. Successful launchers are separately asserted to have empty stderr by the tests.
