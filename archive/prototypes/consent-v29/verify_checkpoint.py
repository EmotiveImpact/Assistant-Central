"""Offline checkpoint preflight; --full runs only the reviewed local test commands.

Checksums establish consistency, not authenticity. Run only trusted checkpoints.
No installation, account setup, browser, or provider connection is performed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile

DOM_SUITES = (
    'owner_ui_dom_check.js', 'workspace_ui_dom_check.js',
    'workspace_ui_review_dom_check.js', 'workspace_composer_dom_check.js',
    'workspace_composer_review_dom_check.js', 'workspace_response_dom_check.js',
    'workspace_response_review_dom_check.js', 'workspace_messages_dom_check.js',
    'workspace_messages_review_dom_check.js', 'workspace_text_exchange_dom_check.js',
    'workspace_text_review_dom_check.js',
    'workspace_relationship_dom_check.js', 'workspace_relationship_review_dom_check.js',
    'workspace_continuity_dom_check.js', 'workspace_continuity_review_dom_check.js',
)
# Full checkpoint evidence requires the optional SDK, even though the default
# application runtime does not. Missing imports/versions block the Python suite.
PINS = {'coincurve': '21.0.0', 'bech32': '1.2.0',
        'cryptography': '50.0.0', 'pydantic': '2.13.4', 'mcp': '1.29.0'}
# Literal code, never loaded from a manifest. -P omits automatic cwd insertion;
# preserve the selected environment, including existing offline PYTHONPATH dependencies.
DEPENDENCY_PROBE = '''import importlib.metadata, json
import coincurve, bech32, pydantic, mcp
from mcp import ClientSession
from mcp.server.lowlevel import Server
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms
from cryptography.hazmat.primitives.asymmetric import x25519
coincurve.PrivateKey(bytes.fromhex('01' * 32)).public_key.format()
x25519.X25519PrivateKey.from_private_bytes(bytes(32)).public_key()
Cipher(algorithms.ChaCha20(bytes(32), bytes(16)), mode=None).encryptor().update(b'fixture')
print(json.dumps({n: importlib.metadata.version(n) for n in
                 ('coincurve', 'bech32', 'cryptography', 'pydantic', 'mcp')}))
'''


def safe_path(root, name):
    """Reject ambiguous/platform-dependent names and symlinks, even inside root."""
    if (not isinstance(name, str) or not name or '\\' in name or ':' in name
            or any(ord(c) < 32 for c in name) or any(not p for p in name.split('/'))):
        raise ValueError('Invalid relative path')
    parts = PurePosixPath(name).parts
    if name.startswith('/') or any(p in ('..', '.') for p in name.split('/')):
        raise ValueError('Unsafe relative path: ' + name)
    path = root
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise ValueError('Symlink not accepted: ' + name)
    if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Missing or unsafe file: ' + name)
    return path


def source_paths(root):
    """Source freeze scope plus local vendor package wrappers (not upstream files)."""
    # unittest discovery can follow package directory symlinks even though
    # pathlib.rglob does not. Reject them before enumerating the freeze scope.
    for folder in ('tests', 'owner_ui', 'workspace_ui', 'vendor'):
        top = root / folder
        if top.is_symlink():
            raise ValueError('Symlink not accepted: ' + folder)
        for directory, dirs, files in os.walk(top, followlinks=False):
            for name in dirs + files:
                path = Path(directory) / name
                if path.is_symlink():
                    raise ValueError('Symlink not accepted: ' + path.relative_to(root).as_posix())
    paths = set(root.glob('*.py')) | set(root.glob('*.js')) | set(root.glob('*.cjs'))
    if any(p.is_symlink() for p in paths):
        raise ValueError('Symlink not accepted in root Python/JavaScript sources')
    paths.update((root / 'vendor').rglob('__init__.py'))
    for folder in ('tests', 'owner_ui', 'workspace_ui'):
        paths.update(p for p in (root / folder).rglob('*')
                     if p.suffix in ('.py', '.js', '.html', '.css'))
    return {p.relative_to(root).as_posix() for p in paths if p.is_file()}


def check_hashes(root, checkpoint=None):
    if checkpoint is None:
        candidates = [(int(m.group(1)), p.name) for p in root.glob('verification-v*.json')
                      if (m := re.fullmatch(r'verification-v(\d+)\.json', p.name))]
        if not candidates:
            raise ValueError('No checkpoint metadata found')
        checkpoint = max(candidates)[1]
    metadata = json.loads(safe_path(root, checkpoint).read_text(encoding='utf-8'))
    if not isinstance(metadata, dict) or not re.fullmatch(r'v\d+', str(metadata.get('checkpoint', ''))):
        raise ValueError('Invalid checkpoint metadata')
    manifest_name = metadata.get('source_hash_manifest')
    manifest = safe_path(root, manifest_name)
    entries = {}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not match:
            raise ValueError('Malformed source hash entry')
        digest, name = match.groups()
        if name in entries or name in (manifest_name, checkpoint):
            raise ValueError('Duplicate or self-referential source entry: ' + name)
        path = safe_path(root, name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Source hash mismatch: ' + name)
        entries[name] = digest
    if not entries or type(metadata.get('source_files_frozen')) is not int or metadata['source_files_frozen'] != len(entries):
        raise ValueError('Source count does not match checkpoint metadata')
    missing = source_paths(root) - entries.keys()
    if missing:
        raise ValueError('Source files missing from freeze: ' + ', '.join(sorted(missing)))
    # Vendored files use the separate upstream manifest, not source freeze entries.
    upstream = json.loads(safe_path(root, 'UPSTREAM.json').read_text(encoding='utf-8'))
    vendors = set()
    if not isinstance(upstream, dict) or not isinstance(upstream.get('files'), list):
        raise ValueError('Invalid upstream manifest')
    for entry in upstream['files']:
        if not isinstance(entry, dict) or not isinstance(entry.get('local'), str) or not isinstance(entry.get('sha256'), str):
            raise ValueError('Invalid upstream hash entry')
        name, digest = entry['local'], entry['sha256']
        if not name.startswith('vendor/') or name in vendors or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('Invalid upstream hash entry')
        if hashlib.sha256(safe_path(root, name).read_bytes()).hexdigest() != digest:
            raise ValueError('Vendored hash mismatch: ' + name)
        vendors.add(name)
    vendor_sources = {p.relative_to(root).as_posix() for p in (root / 'vendor').rglob('*.py')}
    if not vendors or not vendor_sources <= (vendors | entries.keys()):
        raise ValueError('Vendored source missing from upstream manifest')
    return {'checkpoint': metadata['checkpoint'], 'metadata_file': checkpoint,
            'source_hash_manifest': manifest_name, 'sources': len(entries), 'vendored_files': len(vendors)}


def run_command(argv, root, timeout=30):
    """Keep process output out of memory; retain at most its final 6 KiB."""
    with tempfile.TemporaryFile() as output:
        try:
            result = subprocess.run(argv, cwd=root, stdin=subprocess.DEVNULL,
                                    stdout=output, stderr=subprocess.STDOUT,
                                    timeout=timeout, check=False, shell=False)
            code = result.returncode
            status = 'passed' if code == 0 else 'failed'
            reason = None
        except subprocess.TimeoutExpired:
            code, status, reason = None, 'failed', 'Timed out'
        except OSError as exc:
            code, status, reason = None, 'not-run', str(exc)
        size = output.tell()
        output.seek(max(0, size - 6144))
        tail = output.read().decode('utf-8', errors='replace')
    return {'status': status, 'argv': argv, 'exit_code': code, 'reason': reason,
            'output_tail': tail, 'output_truncated': size > 6144}


def verify(root, full=False, checkpoint=None):
    report = {'mode': 'full' if full else 'preflight', 'checks': {}, 'suites': {},
              'platform': sys.platform, 'previously_tested_platform': 'Linux',
              'platform_limits': 'Portable verifier is not cross-platform fixture acceptance. Subprocess-pipe selector behavior may differ on Windows; no Windows or macOS full-runtime acceptance is claimed.',
              'limits': 'Trusted offline fictional fixtures only. No browser, visual, accessibility, live-provider, real-identity or OS-isolation acceptance. Hashes are not authenticated signatures.'}
    checks, suites = report['checks'], report['suites']
    try:
        checks['hashes'] = {'status': 'passed', **check_hashes(root, checkpoint)}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        checks['hashes'] = {'status': 'failed', 'reason': str(exc)[:2000]}
    checks['python'] = {'status': 'passed' if sys.version_info >= (3, 11) else 'failed',
                        'version': sys.version.split()[0]}
    probe = run_command([sys.executable, '-P', '-c', DEPENDENCY_PROBE], root)
    if probe['status'] == 'passed':
        try:
            versions = json.loads(probe['output_tail'])
            probe['versions'] = versions
            if versions != PINS:
                probe.update(status='failed', reason='Installed versions differ from verified pins', expected=PINS)
        except ValueError:
            probe.update(status='failed', reason='Dependency probe returned invalid output')
    checks['python_dependencies'] = probe
    node = shutil.which('node')
    checks['node'] = run_command([node, '--version'], root) if node else {'status': 'not-run', 'reason': 'Node is not installed/on PATH (required for full Python mixed-peer and DOM-model verification)'}
    if checks['node']['status'] == 'passed':
        match = re.fullmatch(r'v(\d+)\.\d+\.\d+\s*', checks['node']['output_tail'])
        if not match or int(match.group(1)) < 18:
            checks['node'].update(status='failed', reason='Node 18 or newer required')
    commands = {'python': [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v']}
    commands.update({name: [node or 'node', 'tests/' + name] for name in DOM_SUITES})
    for name, argv in commands.items():
        reason = None
        if not full:
            reason = 'Not requested; use --full'
        elif checks['hashes']['status'] != 'passed':
            reason = 'Checkpoint integrity preflight failed'
        elif name == 'python' and any(checks[k]['status'] != 'passed' for k in ('python', 'python_dependencies', 'node')):
            reason = 'Python/MCP SDK/mixed-peer prerequisites failed'
        elif name != 'python' and checks['node']['status'] != 'passed':
            reason = 'Node prerequisite unavailable or failed'
        if reason:
            suites[name] = {'status': 'not-run', 'reason': reason}
            continue
        suites[name] = run_command(argv, root, timeout=600)
        if name == 'python' and suites[name]['status'] == 'passed':
            tail = suites[name]['output_tail']
            count = re.search(r'Ran (\d+) tests? in ', tail)
            suites[name]['tests_run'] = int(count.group(1)) if count else None
            if not count or int(count.group(1)) == 0 or re.search(r'skipped=\d+|expected failures=\d+', tail):
                suites[name].update(status='failed', reason='Suite incomplete: no tests or skipped/expected-failure cases; inspect output')
    required = list(checks.values()) + (list(suites.values()) if full else [])
    report['status'] = 'passed' if all(r['status'] == 'passed' for r in required) else 'incomplete-or-failed'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='Run Python and all 15 Node DOM-model suites locally')
    parser.add_argument('--checkpoint', help='Relative checkpoint JSON (default: highest numbered verification-vN.json)')
    args = parser.parse_args(argv)
    report = verify(Path(__file__).resolve().parent, args.full, args.checkpoint)
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
