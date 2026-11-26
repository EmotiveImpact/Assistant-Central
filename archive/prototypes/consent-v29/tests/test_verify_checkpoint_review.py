"""Independent adversarial checks of the local checkpoint verifier."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import verify_checkpoint as verifier


class IndependentHashReview(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        for folder in ('tests', 'vendor', 'owner_ui', 'workspace_ui'):
            (self.root / folder).mkdir()
        (self.root / 'example.py').write_text('# source\n')
        (self.root / 'vendor/example.py').write_text('# vendor\n')
        digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        (self.root / 'freeze.sha256').write_text(digest(self.root / 'example.py') + '  example.py\n')
        (self.root / 'UPSTREAM.json').write_text(json.dumps({'files': [
            {'local': 'vendor/example.py', 'sha256': digest(self.root / 'vendor/example.py')}]}))
        (self.root / 'verification-v22.json').write_text(json.dumps({
            'checkpoint': 'v22', 'source_hash_manifest': 'freeze.sha256', 'source_files_frozen': 1}))

    def test_nested_directory_symlinks_cannot_hide_executable_sources(self):
        outside_temp = tempfile.TemporaryDirectory()
        self.addCleanup(outside_temp.cleanup)
        outside = Path(outside_temp.name)
        (outside / '__init__.py').write_text('')
        (outside / 'test_hidden.py').write_text('import unittest\nclass Hidden(unittest.TestCase):\n def test_hidden(self): pass\n')
        for tree in ('tests', 'vendor', 'owner_ui', 'workspace_ui'):
            with self.subTest(tree=tree):
                link = self.root / tree / 'hidden'
                try:
                    link.symlink_to(outside, target_is_directory=True)
                except (NotImplementedError, OSError) as exc:
                    self.fail('Real symlink regression requires symlink support: ' + str(exc))
                try:
                    with self.assertRaises(ValueError):
                        verifier.check_hashes(self.root)
                finally:
                    link.unlink()

    def test_dangling_symlinks_are_rejected(self):
        link = self.root / 'tests' / 'missing.py'
        link.symlink_to(self.root / 'not-present')
        with self.assertRaises(ValueError):
            verifier.check_hashes(self.root)

    def test_file_path_with_trailing_separator_is_rejected(self):
        with self.assertRaises(ValueError):
            verifier.safe_path(self.root, 'example.py/')

    def test_unfrozen_nested_ui_assets_fail(self):
        for name in ('owner_ui/new.css', 'workspace_ui/new.html', 'tests/new.js'):
            with self.subTest(name=name):
                path = self.root / name
                path.write_text('/* fictional */')
                try:
                    with self.assertRaisesRegex(ValueError, 'missing from freeze'):
                        verifier.check_hashes(self.root)
                finally:
                    path.unlink()

    def test_duplicate_vendor_entries_fail(self):
        path = self.root / 'UPSTREAM.json'
        data = json.loads(path.read_text())
        data['files'] *= 2
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'upstream hash entry'):
            verifier.check_hashes(self.root)


class IndependentExecutionReview(unittest.TestCase):
    def test_real_timeout_is_failure(self):
        result = verifier.run_command([sys.executable, '-c', 'import time; time.sleep(5)'], Path.cwd(), timeout=0.05)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['reason'], 'Timed out')
        self.assertIsNone(result['exit_code'])

    def test_literal_shell_characters_do_not_expand(self):
        argument = '$(echo should-not-expand); & |'
        result = verifier.run_command([sys.executable, '-c', 'import sys; print(sys.argv[1])', argument], Path.cwd())
        self.assertEqual(result['status'], 'passed')
        self.assertEqual(result['output_tail'], argument + '\n')

    def test_dom_nonzero_prevents_overall_success(self):
        def fake_run(argv, root, timeout=30):
            status, output = 'passed', 'DOM fixture passed\n'
            if '-P' in argv:
                output = json.dumps(verifier.PINS)
            elif '--version' in argv:
                output = 'v22.0.0\n'
            elif 'unittest' in argv:
                output = 'Ran 1 test in 0.01s\nOK\n'
            elif argv[-1].endswith(verifier.DOM_SUITES[-1]):
                status = 'failed'
            return {'status': status, 'exit_code': 0 if status == 'passed' else 7, 'output_tail': output}
        with patch.object(verifier, 'check_hashes', return_value={}), patch.object(verifier.shutil, 'which', return_value='/node'), patch.object(verifier, 'run_command', side_effect=fake_run):
            result = verifier.verify(Path.cwd(), full=True)
        self.assertEqual(result['status'], 'incomplete-or-failed')
        self.assertEqual(result['suites'][verifier.DOM_SUITES[-1]]['status'], 'failed')
        self.assertEqual(result['suites']['python']['status'], 'passed')
