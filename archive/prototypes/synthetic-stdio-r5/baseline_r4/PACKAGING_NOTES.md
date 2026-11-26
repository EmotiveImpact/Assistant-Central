# Release finalization and evidence

The independent review recorded 32 implementation tests and 24 separate tests.
The reviewed codec, transport, synthetic stream helpers, implementation tests and
demo remain byte-identical to that review. DESIGN.md subsequently spells out the
notification-silence predicate exactly, and START_HERE_R4.md describes the combined
release checks. These are documentation changes, not a runtime fix.

The independent test bodies and assertions are unchanged. Their import setup was
adapted for both direct execution and package-based unittest discovery: the test
uses a relative bootstrap import when loaded as raw_tests.test_independent_raw.
The bootstrap now prefers the colocated archive's code over an optional external
path, so a fresh-archive run cannot silently test another copy. Original review
test/bootstrap bytes are preserved as text in evidence/ for comparison.

run_all_checks.py and the preserved-baseline manifest are release verification
machinery, outside the independent runtime review. The combined and fresh-archive
runs exercise the final packaged test imports and all inherited checks. The full
source freeze covers those files too. No earlier source tree or archive is edited.

The initial independent hash files reflect the review-stage documentation; the
release's RAW_SOURCE_MANIFEST.json records the final documentation and source.
The extra peer-process concurrent-shutdown/descriptor-lifecycle review remains
uncompleted and is not replaced by any of these checks.
