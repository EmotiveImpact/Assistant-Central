"""Fast guard tests and local TLS controller smoke, not container acceptance."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from network_acceptance.pki import disposable_pki
from network_acceptance.probe import OWNERS, owner_operation, private_write
from network_acceptance.run import Harness, build_context, exercise, main, validate_container, validate_environment, validate_network
from pilot.https_mailbox import MailboxServer, Quarantine, parse_packet


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.mounts = {'/private/atlas': ('own', True), '/quarantine/atlas': ('spool', False)}
        self.container = {
            'Config': {'User': '22001:22001'},
            'HostConfig': {'ReadonlyRootfs': True, 'Privileged': False, 'CapDrop': ['ALL'],
                           'SecurityOpt': ['no-new-privileges:true'], 'NetworkMode': 'isolated',
                           'PidMode': '', 'IpcMode': 'private'},
            'Mounts': [{'Type': 'volume', 'Destination': path, 'Name': volume, 'RW': writable}
                       for path, (volume, writable) in self.mounts.items()],
            'NetworkSettings': {'Networks': {'isolated': {}}}}

    def check(self, value):
        validate_container(value, 22001, 'isolated', self.mounts)

    def test_safe_container_positive_control(self):
        self.check(self.container)

    def test_unsafe_settings_rejected(self):
        mutations = [('Privileged', True), ('ReadonlyRootfs', False), ('CapDrop', []), ('CapAdd', ['SYS_ADMIN']),
                     ('Devices', [{'PathOnHost': '/dev/sda'}]), ('DeviceRequests', [{}]),
                     ('SecurityOpt', []), ('NetworkMode', 'host'), ('PidMode', 'host'), ('IpcMode', 'host'),
                     ('PortBindings', {'8443/tcp': [{'HostPort': '8443'}]}), ('PublishAllPorts', True)]
        for key, value in mutations:
            with self.subTest(setting=key):
                changed = copy.deepcopy(self.container)
                changed['HostConfig'][key] = value
                with self.assertRaises(AssertionError): self.check(changed)

    def test_extra_network_rejected(self):
        self.container['NetworkSettings']['Networks']['bridge'] = {}
        with self.assertRaises(AssertionError): self.check(self.container)

    def test_wrong_uid_or_private_mount_rejected(self):
        for mutation in ('uid', 'bind', 'rw', 'peer'):
            with self.subTest(mutation=mutation):
                changed = copy.deepcopy(self.container)
                if mutation == 'uid': changed['Config']['User'] = '0:0'
                if mutation == 'bind': changed['Mounts'][0]['Type'] = 'bind'
                if mutation == 'rw': changed['Mounts'][1]['RW'] = True
                if mutation == 'peer': changed['Mounts'].append({'Type': 'volume', 'Destination': '/private/beacon', 'Name': 'peer', 'RW': True})
                with self.assertRaises(AssertionError): self.check(changed)

    def test_mailbox_mount_contract_excludes_owner_store(self):
        harness = Harness()
        for owner in OWNERS:
            mounts = harness.mounts('mailbox-' + owner)
            self.assertEqual(set(mounts), {'/tls/' + owner, '/quarantine/' + owner})
            self.assertFalse(harness.mounts('owner-' + owner)['/quarantine/' + owner][1])

    def test_network_requires_internal_bridge(self):
        safe = {'Internal': True, 'Driver': 'bridge', 'EnableIPv6': False}
        validate_network(safe)
        for key, value in [('Internal', False), ('Driver', 'host'), ('EnableIPv6', True)]:
            with self.subTest(key=key), self.assertRaises(AssertionError):
                validate_network({**safe, key: value})

    def environments(self):
        return {kind + '-' + owner: {'uid': uid, 'gid': uid, 'groups': [uid],
                'cap_effective': '0', 'cap_permitted': '0', 'seccomp': '2', 'no_new_privs': '1',
                'interfaces': ['eth0', 'lo'],
                'namespaces': {key: kind + owner + key for key in ('net', 'pid', 'mnt')}}
                for owner, uid in OWNERS.items() for kind in ('owner', 'mailbox')}

    def test_distinct_actual_namespaces_required(self):
        safe = self.environments()
        validate_environment(safe)
        for namespace in ('net', 'pid', 'mnt'):
            with self.subTest(namespace=namespace):
                changed = copy.deepcopy(safe)
                changed['owner-atlas']['namespaces'][namespace] = changed['owner-beacon']['namespaces'][namespace]
                with self.assertRaises(AssertionError): validate_environment(changed)

    def test_actual_security_profile_required(self):
        safe = self.environments()
        for key, value in [('cap_effective', '1'), ('cap_permitted', '1'), ('seccomp', '0'),
                           ('no_new_privs', '0'), ('interfaces', ['lo']), ('groups', [0, 22001])]:
            with self.subTest(key=key):
                changed = copy.deepcopy(safe)
                changed['owner-atlas'][key] = value
                with self.assertRaises(AssertionError): validate_environment(changed)

    def test_build_context_omits_untracked_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            archive = Path(temporary) / 'context.tgz'
            build_context(archive)
            with tarfile.open(archive) as stream:
                names = stream.getnames()
                self.assertIn('pilot/runtime.py', names)
                self.assertIn('network_acceptance/probe.py', names)
                self.assertNotIn('network_acceptance/run.py', names)
                self.assertTrue(all(name == 'Dockerfile' or name.startswith(('pilot/', 'network_acceptance/')) for name in names))
                self.assertFalse(any('.git' in name or name.endswith(('.sqlite', '.pem')) for name in names))

    def test_docker_failure_redacts_stdout_stderr_and_stdin(self):
        result = subprocess.CompletedProcess([], 1, 'SECRET_STDOUT', 'SECRET_STDERR')
        with patch('subprocess.run', return_value=result), self.assertRaises(RuntimeError) as caught:
            Harness().docker('exec', 'test', data='SECRET_PASSWORD')
        self.assertNotIn('SECRET', str(caught.exception))

    def test_unexpected_error_is_not_successful_refusal(self):
        h = Harness()
        h.passwords['atlas'] = 'Fictional password only'
        with patch.object(h, 'docker', return_value=json.dumps({'ok': False, 'error_type': 'OSError'})):
            with self.assertRaises(AssertionError): h.owner('atlas', 'send', expected_error='HTTPSOutcomeUnknown')
        with patch.object(h, 'docker', return_value=json.dumps({'ok': True, 'result': {}})):
            with self.assertRaises(AssertionError): h.owner('atlas', 'send', expected_error='HTTPSOutcomeUnknown')

    def test_missing_docker_never_writes_passing_evidence(self):
        with tempfile.TemporaryDirectory() as temporary, patch('shutil.which', return_value=None):
            path = Path(temporary) / 'result.json'
            with self.assertRaisesRegex(RuntimeError, 'No container acceptance ran'):
                main(['--output', str(path)])
            self.assertFalse(path.exists())

    def test_disposable_ca_distinct_leaf_keys_exact_sans(self):
        ca, leaves = disposable_pki(['mailbox-atlas', 'mailbox-beacon'])
        issuer = x509.load_pem_x509_certificate(ca.encode())
        self.assertTrue(issuer.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
        public_keys = []
        for name, values in leaves.items():
            cert = x509.load_pem_x509_certificate(values['certificate'].encode())
            cert.verify_directly_issued_by(issuer)
            self.assertEqual(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.DNSName), [name])
            public_keys.append(cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.assertNotEqual(*public_keys)
        self.assertNotIn('PRIVATE KEY', ca)


class LocalTLSControllerSmoke(unittest.TestCase):
    """Runs actual helper/TLS operations, simulates only Docker controls.

    This catches controller semantics before hosted CI, but its owner processes
    share this UID/host. It cannot supply actual-container acceptance evidence.
    """
    def test_full_controller_logic_without_claiming_container_isolation(self):
        with tempfile.TemporaryDirectory() as temporary:
            harness = LocalHarness(Path(temporary))
            try:
                result = exercise(harness)
                self.assertTrue(result['outage_retained_uncertain_attempt'])
                self.assertTrue(result['remote_cancellation_only_after_import'])
            finally:
                harness.close()


class LocalHarness:
    def __init__(self, root):
        self.root, self.passwords, self.identities, self.mailboxes = root, {}, {}, {}
        self.ca, leaves = disposable_pki(['localhost'])
        self.wrong_ca, _ = disposable_pki([])
        private_write(root / 'cert', leaves['localhost']['certificate'])
        private_write(root / 'key', leaves['localhost']['key'])
        for owner in OWNERS:
            (root / owner).mkdir(mode=0o700)
            (root / (owner + '-spool')).mkdir(mode=0o700)
            self.passwords[owner] = 'Fictional ' + owner + ' password 2026'
            self.identities[owner] = self.owner(owner, 'provision', ca=self.ca, wrong_ca=self.wrong_ca)
            self.start(owner)

    def start(self, owner):
        q = Quarantine(self.root / (owner + '-spool'), self.identities[owner]['fingerprint'])
        server = MailboxServer(q, self.root / 'cert', self.root / 'key', enabled=True)
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01})
        thread.start()
        self.mailboxes[owner] = (q, server, thread, server.server_address[1], True)

    def stop(self, owner):
        q, server, thread, port, running = self.mailboxes[owner]
        if running:
            server.shutdown(); server.server_close(); thread.join(); q.close()
            self.mailboxes[owner] = (q, server, thread, port, False)

    def owner(self, owner, operation, expected_error=None, password=None, **values):
        if 'target' in values:
            url = urlsplit(values['target'])
            peer = url.hostname.split('-')[-1]
            host = '127.0.0.1' if url.hostname.startswith('wrong-') else 'localhost'
            values['target'] = f'https://{host}:{self.mailboxes[peer][3]}{url.path}'
        try:
            result = owner_operation(self.root / owner, self.root / (owner + '-spool'),
                {'owner': owner, 'operation': operation, 'password': password or self.passwords[owner], **values})
        except Exception as exc:
            if expected_error == type(exc).__name__:
                return {'ok': False, 'error_type': expected_error}
            raise
        if expected_error:
            raise AssertionError('Expected ' + expected_error + ' for ' + operation)
        return result

    def probe(self, role, **request):
        owner = request['owner']
        files = sorted((self.root / (owner + '-spool')).glob('*.json'))
        for path in files:
            raw = path.read_bytes()
            parse_packet(raw)
            assert all(marker.encode() not in raw for marker in request['markers'])
        return {'digests': [path.stem for path in files], 'ciphertext_only': True}

    def name(self, role): return role
    def wait_ready(self, owner): pass
    def boundaries(self): pass  # Explicitly no container proof in this smoke test.

    def docker(self, command, *args):
        role = args[-1]
        if role.startswith('owner-'):
            assert command == 'restart'
            return  # Owner helper already closes/reopens its store each call.
        owner = role.split('-', 1)[1]
        if command in ('stop', 'restart'): self.stop(owner)
        if command in ('start', 'restart'): self.start(owner)

    def close(self):
        for owner in self.mailboxes: self.stop(owner)


if __name__ == '__main__':
    unittest.main()
