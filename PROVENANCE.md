# Public import provenance

This repository imports three recovered source checkpoints and a rebuilt team
coordinator. The team implementation is a replacement, not recovery of the
previous missing local team commit. The components remain separate prototypes.

The original input archive SHA-256 values are retained in `team/BASELINES.json`.
Original backup ZIPs are not republished: their full source trees are expanded in
`prototypes/` and `docs/integration-readiness/` instead.

For public release, private artifact references were removed and machine-specific
paths in historical evidence were normalized. Runtime Python, JavaScript and UI
source and third-party notices are unchanged from the supplied checkpoints.
`docs/publication-cleanup.json` lists normalized evidence files.

Historical verification files are records of their original checkpoints, not
fresh claims about this public import. Old inventory manifests can describe the
pre-normalization evidence; they must not be treated as hashes of every public
documentation byte. Runtime integrity manifests are preserved unchanged. The
public `IMPORT_MANIFEST.json` and regenerated `team/MANIFEST.json` describe this
sanitized import. Run `python -B tools/verify_import.py` to verify them.

The publication review found no actual credentials, private conversation exports
or personal contact details. Public RFC keys and known-answer cryptographic test
vectors are synthetic fixtures and must never be used as real credentials. This
review is not a security certification.

See [current verification](docs/VERIFICATION.md) for fresh test results and limits.
