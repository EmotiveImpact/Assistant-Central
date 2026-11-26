"""Verifier tests use temporary fictional files and mocked suite execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import verify_checkpoint as verifier


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'verification').mkdir()
        (self.root / 'vendor').mkdir()
        (self.root / 'example.py').write_text('# fictional\n')
        (self.root / 'vendor/example.py').write_text('# vendor fixture\n')
        self.upstream = {'files': [{'local': 'vendor/example.py', 'sha256': self.digest('vendor/example.py')}]}
        self.metadata = {'checkpoint': 'v22', 'source_files_frozen': 1,
                         'source_hash_manifest': 'verification/freeze.sha256'}
        self.freeze()

    def digest(self, name):
        return hashlib.sha256((self.root / name).read_bytes()).hexdigest()

    def freeze(self, line=None):
        (self.root / 'UPSTREAM.json').write_text(json.dumps(self.upstream))
        (self.root / 'verification-v22.json').write_text(json.dumps(self.metadata))
        (self.root / 'verification/freeze.sha256').write_text(
            line if line is not None else self.digest('example.py') + '  example.py\n')

    def test_valid_source_and_vendor_hashes(self):
        self.assertEqual(verifier.check_hashes(self.root), {'checkpoint': 'v22', 'metadata_file': 'verification-v22.json',
                         'source_hash_manifest': 'verification/freeze.sha256', 'sources': 1, 'vendored_files': 1})

    def test_latest_checkpoint_is_numeric(self):
        (self.root / 'verification-v9.json').write_text('broken')
        self.assertEqual(verifier.check_hashes(self.root)['checkpoint'], 'v22')

    def test_missing_checkpoint(self):
        (self.root / 'verification-v22.json').unlink()
        with self.assertRaisesRegex(ValueError, 'No checkpoint'):
            verifier.check_hashes(self.root)

    def test_tampered_source(self):
        (self.root / 'example.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            verifier.check_hashes(self.root)

    def test_missing_source(self):
        (self.root / 'example.py').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing'):
            verifier.check_hashes(self.root)

    def test_unfrozen_source(self):
        (self.root / 'new.py').write_text('')
        with self.assertRaisesRegex(ValueError, 'missing from freeze'):
            verifier.check_hashes(self.root)

    def test_duplicate_hash_entry(self):
        line = self.digest('example.py') + '  example.py\n'
        self.freeze(line * 2)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            verifier.check_hashes(self.root)

    def test_malformed_hash_entry(self):
        self.freeze('not a checksum\n')
        with self.assertRaisesRegex(ValueError, 'Malformed'):
            verifier.check_hashes(self.root)

    def test_metadata_source_count(self):
        self.metadata['source_files_frozen'] = True
        self.freeze()
        with self.assertRaisesRegex(ValueError, 'count'):
            verifier.check_hashes(self.root)

    def test_manifest_self_reference_rejected(self):
        self.freeze('0' * 64 + '  verification/freeze.sha256\n')
        with self.assertRaisesRegex(ValueError, 'self-referential'):
            verifier.check_hashes(self.root)

    def test_unsafe_paths(self):
        for name in ('../outside', '/etc/passwd', 'C:/file', 'x\\y', './example.py', 'x//y', 'x/../example.py', 'x\ny', ''):
            with self.subTest(name=name), self.assertRaises(ValueError):
                verifier.safe_path(self.root, name)

    def test_symlink_rejected(self):
        # Mock the predicate for portability to Windows without symlink privilege.
        with patch.object(Path, 'is_symlink', return_value=True):
            with self.assertRaisesRegex(ValueError, 'Symlink'):
                verifier.safe_path(self.root, 'example.py')

    def test_vendor_hash_mismatch(self):
        (self.root / 'vendor/example.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'Vendored hash mismatch'):
            verifier.check_hashes(self.root)

    def test_unlisted_vendor_source(self):
        (self.root / 'vendor/new.py').write_text('')
        with self.assertRaisesRegex(ValueError, 'Vendored source missing'):
            verifier.check_hashes(self.root)

    def test_latest_bad_metadata_does_not_fall_back(self):
        (self.root / 'verification-v23.json').write_text('{broken')
        with self.assertRaises(ValueError):
            verifier.check_hashes(self.root)
        self.assertEqual(verifier.check_hashes(self.root, 'verification-v22.json')['checkpoint'], 'v22')

    def test_local_vendor_wrapper_requires_source_freeze(self):
        (self.root / 'vendor/__init__.py').write_text('# local wrapper')
        with self.assertRaisesRegex(ValueError, 'missing from freeze'):
            verifier.check_hashes(self.root)
        self.metadata['source_files_frozen'] = 2
        self.freeze(self.digest('example.py') + '  example.py\n' +
                    self.digest('vendor/__init__.py') + '  vendor/__init__.py\n')
        self.assertEqual(verifier.check_hashes(self.root)['sources'], 2)

    def test_malformed_upstream_returns_failed_report(self):
        (self.root / 'UPSTREAM.json').write_text('{"files": [{"local": null}]}')
        with self.assertRaisesRegex(ValueError, 'Invalid upstream hash entry'):
            verifier.check_hashes(self.root)

    def test_explicit_metadata_filename_labels_actual_identity(self):
        (self.root / 'named-checkpoint.json').write_text(json.dumps(self.metadata))
        result = verifier.check_hashes(self.root, 'named-checkpoint.json')
        self.assertEqual(result['metadata_file'], 'named-checkpoint.json')
        self.assertEqual(result['checkpoint'], 'v22')
        self.assertEqual(result['source_hash_manifest'], 'verification/freeze.sha256')

    def test_manifest_commands_never_executed(self):
        self.metadata['commands'] = ['do-not-execute']
        self.freeze()
        self.assertEqual(verifier.check_hashes(self.root)['sources'], 1)


class RunTests(unittest.TestCase):
    def test_nonzero_exit_is_failure(self):
        result = verifier.run_command([sys.executable, '-c', 'raise SystemExit(7)'], Path.cwd())
        self.assertEqual((result['status'], result['exit_code']), ('failed', 7))

    def test_bounded_output(self):
        result = verifier.run_command([sys.executable, '-c', "print('x' * 10000)"], Path.cwd())
        self.assertEqual(result['status'], 'passed')
        self.assertTrue(result['output_truncated'])
        self.assertLessEqual(len(result['output_tail']), 6144)

    def test_missing_runtime(self):
        with patch.object(subprocess, 'run', side_effect=FileNotFoundError('missing')):
            self.assertEqual(verifier.run_command(['missing'], Path.cwd())['status'], 'not-run')

    def test_timeout_and_exact_argv_no_shell(self):
        argv = ['python with spaces', 'literal;argument']
        with patch.object(subprocess, 'run', side_effect=subprocess.TimeoutExpired(argv, 1)) as run:
            result = verifier.run_command(argv, Path.cwd(), timeout=1)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(run.call_args.args[0], argv)
        self.assertFalse(run.call_args.kwargs['shell'])
        self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)


class ReportTests(unittest.TestCase):
    def invoke(self, full=False, dependency_status='passed', node=True, hashes=True, python_tail=None, versions=None, probe_output=None, node_version=None):
        self.calls = []
        def fake_run(argv, root, timeout=30):
            self.calls.append(argv)
            status, output = 'passed', 'DOM model passed\n'
            if '-P' in argv:
                status, output = dependency_status, json.dumps(versions if versions is not None else verifier.PINS)
                if probe_output is not None:
                    output = probe_output
            elif '--version' in argv:
                output = node_version if node_version is not None else 'v22.0.0\n'
            elif 'unittest' in argv:
                output = python_tail if python_tail is not None else 'Ran 640 tests in 1s\n\nOK\n'
            return {'status': status, 'output_tail': output, 'exit_code': 0 if status == 'passed' else 1}
        with patch.object(verifier, 'check_hashes', side_effect=None if hashes else ValueError('bad hash'), return_value={}), \
             patch.object(verifier.shutil, 'which', return_value='/installed/node' if node else None), \
             patch.object(verifier, 'run_command', side_effect=fake_run):
            return verifier.verify(Path.cwd(), full=full)

    def test_preflight_does_not_run_suites(self):
        result = self.invoke()
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(all(r['status'] == 'not-run' for r in result['suites'].values()))

    def test_full_runs_exact_known_suites(self):
        result = self.invoke(full=True)
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(len(result['suites']), 1 + len(verifier.DOM_SUITES))
        self.assertEqual(self.calls[2], [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'])
        self.assertEqual(self.calls[3:], [['/installed/node', 'tests/' + name] for name in verifier.DOM_SUITES])

    def test_missing_node_is_not_success(self):
        for full in (False, True):
            result = self.invoke(full=full, node=False)
            self.assertEqual(result['status'], 'incomplete-or-failed')
            self.assertTrue(all(result['suites'][n]['status'] == 'not-run' for n in verifier.DOM_SUITES))

    def test_missing_crypto_does_not_run_python_suite(self):
        result = self.invoke(full=True, dependency_status='failed')
        self.assertEqual(result['suites']['python']['status'], 'not-run')
        self.assertEqual(result['status'], 'incomplete-or-failed')
        self.assertTrue(all(result['suites'][n]['status'] == 'passed' for n in verifier.DOM_SUITES))

    def test_wrong_dependency_versions_fail(self):
        result = self.invoke(full=True, versions={})
        self.assertEqual(result['checks']['python_dependencies']['status'], 'failed')
        self.assertEqual(result['suites']['python']['status'], 'not-run')

    def test_hash_failure_prevents_all_suite_execution(self):
        result = self.invoke(full=True, hashes=False)
        self.assertEqual(len(self.calls), 2)
        self.assertTrue(all(r['status'] == 'not-run' for r in result['suites'].values()))

    def test_skipped_or_empty_python_suite_is_not_success(self):
        for tail in ('Ran 0 tests in 0s\nOK', 'Ran 3 tests in 0s\nOK (skipped=1)', 'no test summary'):
            with self.subTest(tail=tail):
                result = self.invoke(full=True, python_tail=tail)
                self.assertEqual(result['suites']['python']['status'], 'failed')

    def test_malformed_dependency_probe_output(self):
        for output in ('noise\n' + json.dumps(verifier.PINS), 'not-json', '[]', 'null'):
            with self.subTest(output=output):
                result = self.invoke(full=True, probe_output=output)
                self.assertEqual(result['checks']['python_dependencies']['status'], 'failed')
                self.assertEqual(result['suites']['python']['status'], 'not-run')

    def test_old_or_malformed_node_version_blocks_dom(self):
        for version in ('v16.0.0\n', 'garbage', 'v22.0.0\nextra output'):
            with self.subTest(version=version):
                result = self.invoke(full=True, node_version=version)
                self.assertEqual(result['checks']['node']['status'], 'failed')
                self.assertTrue(all(result['suites'][n]['status'] == 'not-run' for n in verifier.DOM_SUITES))

    def test_cli_returns_failure_exit_code(self):
        with patch.object(verifier, 'verify', return_value={'status': 'incomplete-or-failed'}), patch('builtins.print'):
            self.assertEqual(verifier.main([]), 1)
