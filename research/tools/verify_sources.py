"""Verify inert research snapshots without extracting or executing upstream files."""
from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile

ROOT = Path(__file__).resolve().parents[1]

def safe_path(name: str) -> bool:
    p = PurePosixPath(name)
    return not p.is_absolute() and '..' not in p.parts and '\\' not in name

def verify() -> tuple[int, int, int]:
    index = json.loads((ROOT / 'SOURCES.json').read_text())
    total_files = total_bytes = 0
    for source in index['repositories']:
        directory = source['directory']
        assert safe_path(directory)
        base = ROOT / directory
        manifest = json.loads((base / 'MANIFEST.json').read_text())
        assert source['repository'] == manifest['repository']
        assert source['commit'] == manifest['commit']
        assert len(manifest['commit']) == 40
        parts = manifest.get('snapshot_parts')
        if parts:
            chunks = []
            for part in parts:
                assert safe_path(part['path']) and '/' not in part['path']
                chunk = (base / part['path']).read_bytes()
                assert len(chunk) == part['bytes']
                assert hashlib.sha256(chunk).hexdigest() == part['sha256']
                chunks.append(chunk)
            archive = b''.join(chunks)
            assert parts == source['snapshot_parts']
        else:
            archive = (base / 'source.tar.gz').read_bytes()
        assert len(archive) == manifest['snapshot_bytes'] == source['snapshot_bytes']
        assert hashlib.sha256(archive).hexdigest() == manifest['snapshot_sha256'] == source['snapshot_sha256']
        expected = {e['path']: e for e in manifest['files']}
        assert len(expected) == manifest['included_files']
        omissions = {e['path']: e for e in manifest['omissions']}
        assert len(omissions) == manifest['omitted_files']
        assert not (set(expected) & set(omissions))
        assert len(expected) + len(omissions) == manifest['tracked_files']
        seen = set()
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
            for member in tar:
                assert member.name.startswith('source/') and safe_path(member.name)
                assert member.isfile() and member.mode == 0o644
                name = member.name.removeprefix('source/')
                assert '.git' not in PurePosixPath(name).parts
                assert name in expected and name not in seen
                seen.add(name)
                entry = expected[name]
                assert member.size == entry['bytes']
                data = tar.extractfile(member).read()
                assert len(data) == entry['bytes'] == member.size
                assert hashlib.sha256(data).hexdigest() == entry['sha256']
                assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == entry['git_blob']
                if name in manifest['licence_paths']:
                    assert (base / 'licences' / name).read_bytes() == data
                total_bytes += len(data)
        assert seen == set(expected)
        actual_licences = {p.relative_to(base / 'licences').as_posix() for p in (base / 'licences').rglob('*') if p.is_file()}
        assert actual_licences == set(manifest['licence_paths'])
        total_files += len(seen)
    return len(index['repositories']), total_files, total_bytes

if __name__ == '__main__':
    repos, files, size = verify()
    print(f'Verified {repos} pinned snapshots, {files} byte-identical source files, {size} uncompressed bytes.')
