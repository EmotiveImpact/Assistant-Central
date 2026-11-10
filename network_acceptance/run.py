"""Actual isolated-container HTTPS acceptance; never falls back to loopback.

Use only an already authorised Docker engine. No engine install, sudo, host
security changes, host ports, Docker socket mounts or real credentials.
"""
import argparse
import json
import ipaddress
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

from .pki import disposable_pki
from .probe import OWNERS, PORT

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'assistant-central.network-acceptance'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def validate_container(info, uid, network, expected_mounts):
    config, host = info['Config'], info['HostConfig']
    require(config['User'] == f'{uid}:{uid}', 'Wrong container UID/GID')
    require(host['ReadonlyRootfs'] and not host['Privileged'], 'Unsafe root filesystem/privilege')
    require({str(cap).upper() for cap in host['CapDrop']} == {'ALL'}, 'Capabilities not dropped')
    require(not host.get('CapAdd') and not host.get('Devices') and not host.get('DeviceRequests'), 'Extra devices/capabilities')
    require(any(value in ('no-new-privileges', 'no-new-privileges:true') for value in host['SecurityOpt']), 'Missing no-new-privileges')
    require(host['NetworkMode'] == network, 'Unexpected network mode')
    require(not host.get('PortBindings') and not host.get('PublishAllPorts'), 'Published host ports')
    require(not host.get('PidMode') and host.get('IpcMode') == 'private', 'Shared PID/IPC')
    actual = {mount['Destination']: (mount.get('Name'), mount['RW'])
              for mount in info['Mounts'] if mount['Type'] != 'tmpfs'}
    require(all(mount['Type'] in ('volume', 'tmpfs') for mount in info['Mounts']), 'Unexpected bind mount')
    require(actual == expected_mounts, 'Unexpected private volumes or write permissions')
    require(set(info['NetworkSettings']['Networks']) == {network}, 'Extra network attachment')


def validate_environment(observed):
    for role, info in observed.items():
        owner = role.split('-', 1)[1]
        uid = OWNERS[owner]
        require(info['uid'] == info['gid'] == uid and set(info['groups']) <= {uid}, 'Wrong process identity')
        require(int(info['cap_effective'], 16) == int(info['cap_permitted'], 16) == 0, 'Process capabilities retained')
        require(info['seccomp'] == '2' and info['no_new_privs'] == '1', 'Process security profile missing')
        require('lo' in info['interfaces'] and len(info['interfaces']) == 2, 'Expected one private bridge interface')
    for namespace in ('net', 'mnt', 'pid'):
        require(len({info['namespaces'][namespace] for info in observed.values()}) == len(observed),
                'Containers share ' + namespace + ' namespace')


def validate_network(info):
    require(info['Internal'] is True and info['Driver'] == 'bridge', 'Network must be an internal bridge')
    require(info.get('EnableIPv6') is False, 'Unexpected IPv6 network')


def build_context(destination):
    # Explicit versioned-code allowlist. Never build with the checkout as context.
    tracked = subprocess.run(['git', 'ls-files', 'pilot'], cwd=ROOT, check=True,
                             stdout=subprocess.PIPE, text=True).stdout.splitlines()
    files = [name for name in tracked if Path(name).suffix in ('.py', '.mjs', '.css', '.html')
             or name == 'pilot/requirements.txt']
    files += ['network_acceptance/__init__.py', 'network_acceptance/probe.py']
    with tarfile.open(destination, 'w:gz') as archive:
        for name, target in [('network_acceptance/Dockerfile', 'Dockerfile')] + [(name, name) for name in files]:
            path = ROOT / name
            require(path.is_file() and not path.is_symlink(), 'Build input is not a regular file')
            archive.add(path, arcname=target, recursive=False)


class Harness:
    def __init__(self):
        self.prefix = 'ac-https-' + secrets.token_hex(6)
        self.image, self.network = self.prefix + ':test', self.prefix + '-net'
        self.containers, self.volumes = [], []
        self.build_started = self.network_started = False
        self.passwords, self.identities = {}, {}

    def name(self, role):
        return self.prefix + '-' + role

    def docker(self, *args, data=None, timeout=60):
        try:
            response = subprocess.run(['docker', *args], input=data, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE, text=True, timeout=timeout)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            raise RuntimeError('Docker unavailable or timed out: ' + args[0]) from None
        if response.returncode:
            # stdin can contain fictional credentials and disposable TLS keys.
            raise RuntimeError('Docker operation failed: ' + args[0] + ' (exit ' + str(response.returncode) + ')')
        return response.stdout

    def prepare(self):
        if shutil.which('docker') is None:
            raise RuntimeError('Docker CLI unavailable. No container acceptance ran; use the dedicated CI job.')
        self.docker('info', '--format', '{{.ServerVersion}}')
        with tempfile.TemporaryDirectory(prefix=self.prefix) as temporary:
            context = Path(temporary) / 'context.tar.gz'
            build_context(context)
            with context.open('rb') as stream:
                self.build_started = True
                result = subprocess.run(['docker', 'build', '--tag', self.image, '-'], stdin=stream,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
            if result.returncode:
                # Context contains only the allowlisted code, never runtime state.
                print(result.stdout.decode(errors='replace')[-4000:], file=sys.stderr)
                raise RuntimeError('Image build failed')
        self.network_started = True
        self.docker('network', 'create', '--internal', '--driver', 'bridge', '--label', LABEL + '=' + self.prefix, self.network)
        validate_network(json.loads(self.docker('network', 'inspect', self.network))[0])
        ca, leaves = disposable_pki(['mailbox-' + owner for owner in OWNERS])
        wrong_ca, _ = disposable_pki([])
        for owner, uid in OWNERS.items():
            for kind in ('owner', 'quarantine', 'tls'):
                volume = self.name(owner + '-' + kind)
                self.volumes.append(volume)
                self.docker('volume', 'create', '--label', LABEL + '=' + self.prefix, volume)
            self.start('owner-' + owner, uid)
            self.passwords[owner] = secrets.token_urlsafe(32)
            self.identities[owner] = self.owner(owner, 'provision', ca=ca, wrong_ca=wrong_ca)
            role = 'mailbox-' + owner
            # Configure using a short-lived network-disabled helper with only its
            # own TLS/quarantine mounts, then start the actual mailbox process.
            self.start(role, uid, network='none')
            self.probe(role, operation='mailbox_setup', owner=owner,
                       recipient=self.identities[owner]['fingerprint'], **leaves[role])
            self.docker('rm', '--force', self.name(role))
            self.containers.remove(self.name(role))
            self.start(role, uid, command=('python', '-B', '-m', 'network_acceptance.probe', 'serve', owner))
            self.wait_ready(owner)
        require(self.identities['atlas']['fingerprint'] != self.identities['beacon']['fingerprint'], 'Shared owner identity')

    def mounts(self, role):
        kind, owner = role.split('-', 1)
        if kind == 'owner':
            return {f'/private/{owner}': (self.name(owner + '-owner'), True),
                    f'/quarantine/{owner}': (self.name(owner + '-quarantine'), False)}
        return {f'/tls/{owner}': (self.name(owner + '-tls'), True),
                f'/quarantine/{owner}': (self.name(owner + '-quarantine'), True)}

    def start(self, role, uid, *, network=None, command=()):
        name = self.name(role)
        self.containers.append(name)
        args = ['run', '--detach', '--init', '--name', name, '--label', LABEL + '=' + self.prefix,
                '--user', f'{uid}:{uid}', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
                '--ipc=private', '--pids-limit=64', '--memory=256m', '--cpus=1', '--network', network or self.network,
                '--tmpfs', f'/tmp:rw,noexec,nosuid,nodev,size=16m,mode=700,uid={uid},gid={uid}']
        if network != 'none':
            args += ['--network-alias', role, '--network-alias', 'wrong-' + role]
        for path, (volume, writable) in self.mounts(role).items():
            args += ['--mount', 'type=volume,source=' + volume + ',target=' + path + ('' if writable else ',readonly')]
        self.docker(*args, self.image, *command)

    def inspect(self, role):
        return json.loads(self.docker('inspect', self.name(role)))[0]

    def probe(self, role, **request):
        response = json.loads(self.docker('exec', '-i', self.name(role), 'python', '-B', '-m',
                                          'network_acceptance.probe', data=json.dumps(request)))
        require(response.get('ok') is True, 'Unexpected fixture response for ' + role + '/' + request['operation'] + ': ' + response.get('error_type', 'invalid response'))
        return response['result']

    def owner(self, owner, operation, *, expected_error=None, password=None, **values):
        request = {'operation': operation, 'owner': owner,
                   'password': self.passwords[owner] if password is None else password, **values}
        response = json.loads(self.docker('exec', '-i', self.name('owner-' + owner), 'python', '-B', '-m',
                                          'network_acceptance.probe', data=json.dumps(request)))
        if expected_error:
            require(response == {'ok': False, 'error_type': expected_error}, 'Expected precise refusal/unknown outcome: ' + operation)
            return response
        require(response.get('ok') is True, 'Owner operation failed: ' + owner + '/' + operation + ' ' + response.get('error_type', 'invalid response'))
        return response['result']

    def wait_ready(self, owner):
        role = 'mailbox-' + owner
        for _ in range(100):
            info = self.inspect(role)
            require(info['State']['Running'], 'Mailbox exited before readiness: ' + role)
            lines = self.docker('logs', self.name(role)).splitlines()
            if lines and json.loads(lines[-1]) == {'ready': True, 'tls_minimum': 'TLSv1.3'}:
                ready = self.probe('owner-' + owner, operation='tls_probe', owner=owner, peer=owner)
                if ready.get('ready') is True:
                    require(ready['version'] == 'TLSv1.3', 'TLS version differs')
                    require(not ipaddress.ip_address(ready['peer_address']).is_loopback, 'TLS peer is loopback')
                    return
            time.sleep(0.1)
        raise RuntimeError('Mailbox readiness timed out')

    def boundaries(self):
        observed = {}
        for owner, uid in OWNERS.items():
            for kind in ('owner', 'mailbox'):
                role = kind + '-' + owner
                validate_container(self.inspect(role), uid, self.network, self.mounts(role))
                observed[role] = self.probe(role, operation='environment')
        validate_environment(observed)
        return {'distinct_network_namespaces': 4, 'distinct_pid_and_mount_namespaces': 4,
                'internal_bridge': True, 'host_ports_published': 0,
                'mailbox_has_owner_store': False, 'owner_quarantine_mount_read_only': True,
                'nonroot_uids': list(OWNERS.values()), 'capabilities_dropped': True}

    def cleanup(self):
        failures = []
        label = 'label=' + LABEL + '=' + self.prefix
        try:
            containers = set(self.docker('ps', '-a', '--filter', label, '--format', '{{.Names}}').splitlines()) if self.containers else set()
            volumes = set(self.docker('volume', 'ls', '--filter', label, '--format', '{{.Name}}').splitlines()) if self.volumes else set()
            networks = set(self.docker('network', 'ls', '--filter', label, '--format', '{{.Name}}').splitlines()) if self.network_started else set()
        except RuntimeError:
            raise RuntimeError('Cleanup state unknown; inspect only label ' + LABEL + '=' + self.prefix) from None
        for name in reversed(self.containers):
            if name in containers:
                try: self.docker('rm', '--force', name)
                except RuntimeError: failures.append(name)
        for name in self.volumes:
            if name in volumes:
                try: self.docker('volume', 'rm', name)
                except RuntimeError: failures.append(name)
        if self.network in networks:
            try: self.docker('network', 'rm', self.network)
            except RuntimeError: failures.append(self.network)
        if self.build_started:
            try:
                tags = self.docker('image', 'ls', '--format', '{{.Repository}}:{{.Tag}}').splitlines()
                if self.image in tags:
                    self.docker('image', 'rm', self.image)
            except RuntimeError: failures.append(self.image)
        if failures:
            raise RuntimeError('Cleanup incomplete; inspect only: ' + ', '.join(failures))


def exercise(h):
    a, b = 'atlas', 'beacon'
    fp = {owner: value['fingerprint'] for owner, value in h.identities.items()}
    targets = {owner: f'https://mailbox-{owner}:{PORT}/v1/quarantine' for owner in OWNERS}
    marker = 'SYNTHETIC_PRIVATE_PAYLOAD_' + secrets.token_hex(16)
    result_marker = 'SYNTHETIC_PRIVATE_RESULT_' + secrets.token_hex(16)

    def state(owner): return h.owner(owner, 'state')
    def item(owner, identifier): return h.owner(owner, 'item', id=identifier)['state']
    def outbox(owner, message): return h.owner(owner, 'outbox', message_id=message)
    def send(sender, receiver, message, **kwargs):
        return h.owner(sender, 'send', message_id=message, target=targets[receiver], recipient=fp[receiver], **kwargs)
    def incoming(sender, receiver, sent, **kwargs):
        return h.owner(receiver, 'import', file_digest=sent['file_digest'], sender=fp[sender], **kwargs)
    def transfer(sender, receiver, message):
        sent = send(sender, receiver, message)
        require(sent['transport_acknowledged'] and sent['delivery'] == 'uncertain' and
                not sent['authorises_execution'] and sent['owner_acceptance'] == 'not_established', 'ACK became authority')
        return sent, incoming(sender, receiver, sent)
    def propose(owner, peer, text, **values):
        return h.owner(owner, 'propose', recipient=fp[peer], text=text, **values)['id']
    def release(owner, identifier): return h.owner(owner, 'release', id=identifier)['message_id']

    for owner, peer in ((a, b), (b, a)):
        h.owner(owner, 'state', password=h.passwords[peer], expected_error='AuthError')
    # Respect the real persisted one-failure authentication delay.
    time.sleep(1.05)
    h.owner(a, 'enrol', **h.identities[b])
    task = propose(a, b, marker)
    require(not state(b)['items'], 'Unreleased proposal crossed boundary')
    message = release(a, task)
    original = outbox(a, message)
    # Each failure is a separately chosen operation, never a product auto-retry.
    send(a, b, message, ca=None, expected_error='HTTPSOutcomeUnknown')
    send(a, b, message, ca='wrong-ca.pem', retry=True, expected_error='HTTPSOutcomeUnknown')
    h.owner(a, 'send', message_id=message, target=targets[b].replace('mailbox-', 'wrong-mailbox-'),
            recipient=fp[b], retry=True, expected_error='HTTPSOutcomeUnknown')
    q = h.probe('mailbox-' + b, operation='quarantine', owner=b, markers=[marker])
    require(not q['digests'], 'Untrusted TLS delivered a packet')
    sent = send(a, b, message, retry=True)
    require(sent['file_digest'] == original['file_digest'], 'Retry resealed packet')
    require(not state(b)['items'] and item(a, task) == 'released', 'Quarantine ACK imported/accepted work')
    require(all(row['state'] == 'uncertain' for row in h.owner(a, 'attempts', message_id=message)['attempts']), 'ACK changed journal')
    incoming(a, b, sent, expected_error='TransportDenied')  # TLS is not enrolment.
    h.owner(b, 'enrol', **h.identities[a])
    h.owner(b, 'import', file_digest=sent['file_digest'], sender=fp[b], expected_error='RuntimeDenied')
    imported = incoming(a, b, sent)
    require(imported['owner_acceptance'] == 'not_established' and item(b, task) == 'pending', 'Import accepted work')
    receipt = h.owner(b, 'send_receipt', message_id=message, target=targets[a], recipient=fp[a])
    require(outbox(a, message)['state'] != 'received', 'Receipt ACK became signed import')
    incoming(b, a, receipt)
    require(outbox(a, message)['state'] == 'received' and item(a, task) == 'released', 'Receipt became acceptance')
    require(incoming(a, b, sent)['duplicate'], 'Duplicate import not recognised')
    repeated = h.owner(b, 'send_receipt', message_id=message, target=targets[a], recipient=fp[a], retry=True)
    require(repeated['file_digest'] == receipt['file_digest'], 'Duplicate receipt renewed bytes')
    damaged = h.owner(a, 'tampered_send', message_id=message, target=targets[b], recipient=fp[b])
    incoming(a, b, damaged, expected_error='TransportDenied')
    require(len(state(b)['items']) == 1, 'Tampered ciphertext created an item')
    decision = h.owner(b, 'accept', id=task)
    transfer(b, a, 'decision-' + decision['decision_digest'])
    require(item(a, task) == 'accepted', 'Explicit signed decision not applied')
    artifact = propose(b, a, result_marker, kind='artifact', parent_id=task)
    transfer(b, a, release(b, artifact))
    require(item(a, artifact) == 'pending', 'Returned artifact auto-accepted')
    h.owner(a, 'accept', id=artifact)

    offline = propose(a, b, marker + '_OUTAGE', task_id='fictional-outage')
    offline_message = release(a, offline)
    before = outbox(a, offline_message)
    h.docker('stop', '--time', '1', h.name('mailbox-' + b))
    send(a, b, offline_message, expected_error='HTTPSOutcomeUnknown')
    uncertain = h.owner(a, 'attempts', message_id=offline_message)['attempts']
    require(len(uncertain) == 1 and uncertain[0]['state'] == 'uncertain', 'Outage not durably uncertain')
    h.docker('restart', '--time', '1', h.name('owner-' + a))
    require(outbox(a, offline_message)['file_digest'] == before['file_digest'], 'Restart changed retained packet')
    require(h.owner(a, 'attempts', message_id=offline_message)['attempts'] == uncertain, 'Restart lost attempts')
    send(a, b, offline_message, expected_error='RuntimeDenied')
    h.docker('start', h.name('mailbox-' + b))
    h.wait_ready(b)
    recovered = send(a, b, offline_message, retry=True)
    require(recovered['file_digest'] == before['file_digest'], 'Outage retry resealed packet')
    incoming(a, b, recovered)
    require(item(b, offline) == 'pending', 'Outage recovery accepted work')

    cancellation = h.owner(a, 'cancel', id=offline)
    count = len(h.owner(a, 'attempts', message_id=offline_message)['attempts'])
    send(a, b, offline_message, retry=True, expected_error='RuntimeDenied')
    require(len(h.owner(a, 'attempts', message_id=offline_message)['attempts']) == count, 'Cancelled resend consumed attempt')
    require(item(b, offline) == 'pending', 'Unobserved cancellation changed peer')
    transfer(a, b, cancellation['cancel_message_id'])
    require(item(b, offline) == 'cancelled', 'Observed cancellation not applied')
    require(incoming(a, b, recovered)['duplicate'] and item(b, offline) == 'cancelled', 'Duplicate revived cancelled work')
    h.owner(b, 'accept', id=offline, expected_error='RuntimeDenied')
    persisted = {owner: state(owner) for owner in OWNERS}
    quarantine = {}
    for owner in OWNERS:
        quarantine[owner] = h.probe('mailbox-' + owner, operation='quarantine', owner=owner,
                                    markers=[marker, result_marker, *h.passwords.values()])
        require(quarantine[owner]['digests'], 'Ciphertext inspection lacked positive control')
        h.docker('restart', '--time', '1', h.name('owner-' + owner))
        h.docker('restart', '--time', '1', h.name('mailbox-' + owner))
        h.wait_ready(owner)
        require(state(owner) == persisted[owner], 'Restart changed identity/items/audit')
        require(h.probe('mailbox-' + owner, operation='quarantine', owner=owner,
                        markers=[marker, result_marker]) == quarantine[owner], 'Restart changed quarantine')
        require(persisted[owner]['provider_store_present'] is False, 'Provider enabled')
    h.boundaries()  # Recheck namespace and mount guards after real restarts.
    return {'verified_tls_minimum': 'TLSv1.3', 'untrusted_ca_and_wrong_hostname_rejected': True,
            'tls_is_not_peer_enrolment': True, 'wrong_sender_and_tampered_ciphertext_rejected': True,
            'quarantine_is_not_import': True, 'signed_receipt_is_not_acceptance': True,
            'explicit_recipient_decision': True, 'origin_only_artifact_return': True,
            'outage_retained_uncertain_attempt': True, 'restart_preserved_original_packets_and_history': True,
            'retry_requires_explicit_choice': True, 'duplicate_receipt_bytes_preserved': True,
            'cancelled_resend_blocked': True, 'remote_cancellation_only_after_import': True,
            'duplicate_did_not_revive_cancelled_work': True, 'quarantine_plaintext_markers_absent': True,
            'provider_calls': 0}


def run():
    harness = Harness()
    try:
        harness.prepare()
        topology = harness.boundaries()
        result = exercise(harness)
        return {'schema': 'assistant-central-network-acceptance/1', 'result': 'passed',
                'synthetic_only': True, 'topology': topology, 'exchange': result,
                'real_people_enrolled': False, 'separate_physical_hosts_tested': False,
                'internet_deployment_tested': False, 'production_security_certification': False}
    finally:
        original = sys.exc_info()[1]
        try:
            harness.cleanup()
        except RuntimeError as cleanup_error:
            if original:
                raise RuntimeError(str(original) + '; ' + str(cleanup_error)) from None
            raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    result = run()  # Never write a passing artifact on partial/failed acceptance.
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
