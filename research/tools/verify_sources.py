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

def require(condition: bool, message: str) -> None:
    """Integrity checks must remain active when Python optimisation is enabled."""
    if not condition:
        raise ValueError(message)

def verify() -> tuple[int, int, int]:
    index = json.loads((ROOT / 'SOURCES.json').read_text())
    total_files = total_bytes = 0
    for source in index['repositories']:
        directory = source['directory']
        require(safe_path(directory), 'Research snapshot validation failed: safe_path(directory)')
        base = ROOT / directory
        manifest = json.loads((base / 'MANIFEST.json').read_text())
        require(source['repository'] == manifest['repository'], "Research snapshot validation failed: source['repository'] == manifest['repository']")
        require(source['commit'] == manifest['commit'], "Research snapshot validation failed: source['commit'] == manifest['commit']")
        require(len(manifest['commit']) == 40, "Research snapshot validation failed: len(manifest['commit']) == 40")
        parts = manifest.get('snapshot_parts')
        if parts:
            chunks = []
            for part in parts:
                require(safe_path(part['path']) and '/' not in part['path'], "Research snapshot validation failed: safe_path(part['path']) and '/' not in part['path']")
                chunk = (base / part['path']).read_bytes()
                require(len(chunk) == part['bytes'], "Research snapshot validation failed: len(chunk) == part['bytes']")
                require(hashlib.sha256(chunk).hexdigest() == part['sha256'], "Research snapshot validation failed: hashlib.sha256(chunk).hexdigest() == part['sha256']")
                chunks.append(chunk)
            archive = b''.join(chunks)
            require(parts == source['snapshot_parts'], "Research snapshot validation failed: parts == source['snapshot_parts']")
        else:
            archive = (base / 'source.tar.gz').read_bytes()
        require(len(archive) == manifest['snapshot_bytes'] == source['snapshot_bytes'], "Research snapshot validation failed: len(archive) == manifest['snapshot_bytes'] == source['snapshot_bytes']")
        require(hashlib.sha256(archive).hexdigest() == manifest['snapshot_sha256'] == source['snapshot_sha256'], "Research snapshot validation failed: hashlib.sha256(archive).hexdigest() == manifest['snapshot_sha256'] == source['snapshot_sha256']")
        expected = {e['path']: e for e in manifest['files']}
        require(len(expected) == manifest['included_files'], "Research snapshot validation failed: len(expected) == manifest['included_files']")
        omissions = {e['path']: e for e in manifest['omissions']}
        require(len(omissions) == manifest['omitted_files'], "Research snapshot validation failed: len(omissions) == manifest['omitted_files']")
        require(not (set(expected) & set(omissions)), 'Research snapshot validation failed: not (set(expected) & set(omissions))')
        require(len(expected) + len(omissions) == manifest['tracked_files'], "Research snapshot validation failed: len(expected) + len(omissions) == manifest['tracked_files']")
        seen = set()
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
            for member in tar:
                require(member.name.startswith('source/') and safe_path(member.name), "Research snapshot validation failed: member.name.startswith('source/') and safe_path(member.name)")
                require(member.isfile() and member.mode == 0o644, 'Research snapshot validation failed: member.isfile() and member.mode == 0o644')
                name = member.name.removeprefix('source/')
                require('.git' not in PurePosixPath(name).parts, "Research snapshot validation failed: '.git' not in PurePosixPath(name).parts")
                require(name in expected and name not in seen, 'Research snapshot validation failed: name in expected and name not in seen')
                seen.add(name)
                entry = expected[name]
                require(member.size == entry['bytes'], "Research snapshot validation failed: member.size == entry['bytes']")
                data = tar.extractfile(member).read()
                require(len(data) == entry['bytes'] == member.size, "Research snapshot validation failed: len(data) == entry['bytes'] == member.size")
                require(hashlib.sha256(data).hexdigest() == entry['sha256'], "Research snapshot validation failed: hashlib.sha256(data).hexdigest() == entry['sha256']")
                require(hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == entry['git_blob'], "Research snapshot validation failed: hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\\0' + data).hexdigest() == entry['git_blob']")
                if name in manifest['licence_paths']:
                    require((base / 'licences' / name).read_bytes() == data, "Research snapshot validation failed: (base / 'licences' / name).read_bytes() == data")
                total_bytes += len(data)
        require(seen == set(expected), 'Research snapshot validation failed: seen == set(expected)')
        actual_licences = {p.relative_to(base / 'licences').as_posix() for p in (base / 'licences').rglob('*') if p.is_file()}
        require(actual_licences == set(manifest['licence_paths']), "Research snapshot validation failed: actual_licences == set(manifest['licence_paths'])")
        total_files += len(seen)
    return len(index['repositories']), total_files, total_bytes

if __name__ == '__main__':
    repos, files, size = verify()
    print(f'Verified {repos} pinned snapshots, {files} byte-identical source files, {size} uncompressed bytes.')
