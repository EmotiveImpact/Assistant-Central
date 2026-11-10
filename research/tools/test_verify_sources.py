"""Check our verifier with inert fixtures, including under Python -O."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SnapshotVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='research-verifier-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'tools').mkdir()
        shutil.copyfile(ROOT / 'tools/verify_sources.py', self.root / 'tools/verify_sources.py')
        sources = json.loads((ROOT / 'SOURCES.json').read_text())['repositories']
        self.source = copy.deepcopy(min(sources, key=lambda s: s['snapshot_bytes']))
        self.base = self.root / self.source['directory']
        shutil.copytree(ROOT / self.source['directory'], self.base)
        self.manifest = json.loads((self.base / 'MANIFEST.json').read_text())
        self.write_metadata()

    def write_metadata(self):
        (self.root / 'SOURCES.json').write_text(json.dumps({'repositories': [self.source]}))
        (self.base / 'MANIFEST.json').write_text(json.dumps(self.manifest))

    def check(self, valid):
        for optimised in (False, True):
            with self.subTest(optimised=optimised):
                command = [sys.executable, '-I', '-B']
                if optimised:
                    command.append('-O')
                command.append(str(self.root / 'tools/verify_sources.py'))
                result = subprocess.run(command, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode == 0, valid, result.stdout + result.stderr)
                if not valid:
                    self.assertIn('Research snapshot validation failed:', result.stderr)

    def replace_archive(self, data):
        (self.base / 'source.tar.gz').write_bytes(data)
        for target in (self.source, self.manifest):
            target['snapshot_bytes'] = len(data)
            target['snapshot_sha256'] = hashlib.sha256(data).hexdigest()
        self.write_metadata()

    def test_baseline(self):
        self.check(True)

    def test_corrupt_archive(self):
        path = self.base / 'source.tar.gz'
        data = bytearray(path.read_bytes())
        data[-1] ^= 1
        path.write_bytes(data)
        self.check(False)

    def test_wrong_git_blob(self):
        self.manifest['files'][0]['git_blob'] = '0' * 40
        self.write_metadata()
        self.check(False)

    def test_changed_licence(self):
        path = self.base / 'licences' / self.manifest['licence_paths'][0]
        path.write_bytes(path.read_bytes() + b'\nchanged')
        self.check(False)

    def check_member(self, name, mode=0o644, kind=tarfile.REGTYPE):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as archive:
            member = tarfile.TarInfo(name)
            member.mode = mode
            member.type = kind
            if kind == tarfile.SYMTYPE:
                member.linkname = '/outside'
            archive.addfile(member)
        self.replace_archive(stream.getvalue())
        self.check(False)

    def test_traversal(self):
        self.check_member('source/../outside')

    def test_absolute(self):
        self.check_member('/outside')

    def test_executable(self):
        self.check_member('source/README.md', mode=0o755)

    def test_symlink(self):
        self.check_member('source/README.md', kind=tarfile.SYMTYPE)


if __name__ == '__main__':
    unittest.main()
