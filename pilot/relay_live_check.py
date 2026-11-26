"""Check a deployed relay end to end with two fictional owners.

    python -B -m pilot.relay_live_check https://<relay>

Creates two throwaway owners in a temporary folder, registers a mailbox for
each on the relay, sends one encrypted packet from Alice to Bob, imports it,
returns Bob's signed receipt and checks that Alice's copy shows it as released.
Nothing real is sent: the text is fictional and the folder is deleted after.
"""
import hashlib
import sys
import tempfile
import time
from pathlib import Path

from relay.acrelay.client import RelayClient

from .auth import LocalOwnerAuth
from .file_exchange import FileExchange
from .https_mailbox import Quarantine
from .relay_carrier import fetch_into, send_file
from .runtime import PilotRuntime


def _owner(root, name):
    auth = LocalOwnerAuth(root / name)
    auth.bootstrap(name, name + '-assistant', 'fictional-password-' + name)
    session = auth.login('fictional-password-' + name)
    runtime = PilotRuntime(root / name, auth)
    return auth, session, runtime, FileExchange(runtime)


def run(url, say=print):
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        owners = [_owner(root, 'alice'), _owner(root, 'bob')]
        queues = []
        try:
            (_, a_session, a_rt, a_fx), (_, b_session, b_rt, b_fx) = owners
            a_rt.enrol_peer(a_session, b_rt.identity, b_rt.fingerprint)
            b_rt.enrol_peer(b_session, a_rt.identity, a_rt.fingerprint)
            item = a_rt.propose(a_session, b_rt.fingerprint, 'task', 'Fictional check',
                                'Fictional text for a relay check.', 'a' * 64, 'check', int(time.time()) + 900)
            message_id = a_rt.release(a_session, item['id'],
                                      a_rt.review(a_session, item['id'])['review_digest'])['message_id']
            alice_box, bob_box = RelayClient(url), RelayClient(url)
            alice_box.register()
            bob_box.register()
            say('1. Registered two mailboxes.')
            to_bob = bob_box.create_invite(b_rt.fingerprint, packets=2)['link']
            to_alice = alice_box.create_invite(a_rt.fingerprint, packets=2)['link']
            spools = {}
            for name, rt in (('alice', a_rt), ('bob', b_rt)):
                spool = root / ('quarantine-' + name)
                spool.mkdir(mode=0o700)
                spools[name] = (spool, Quarantine(spool, rt.fingerprint))
                queues.append(spools[name][1])
            packet, receipt = root / 'packet.json', root / 'receipt.json'
            a_fx.export(a_session, message_id, packet)
            sent = send_file(packet, to_bob, b_rt.fingerprint)
            if not sent['relay_stored']:
                raise RuntimeError('The relay did not store the packet.')
            say('2. Alice sent one encrypted packet.')
            spool, quarantine = spools['bob']
            got = fetch_into(bob_box, quarantine)
            if got['stored'] != [hashlib.sha256(packet.read_bytes()).hexdigest() + '.json']:
                raise RuntimeError('Bob did not receive exactly the packet Alice sent.')
            if bob_box.fetch()['packets']:
                raise RuntimeError('The relay kept a packet after it was acknowledged.')
            b_fx.receive(b_session, spool / got['stored'][0], receipt)
            say('3. Bob fetched and imported it; the relay deleted its copy.')
            if not send_file(receipt, to_alice, a_rt.fingerprint)['relay_stored']:
                raise RuntimeError('The relay did not store the receipt.')
            spool, quarantine = spools['alice']
            back = fetch_into(alice_box, quarantine)
            if len(back['stored']) != 1:
                raise RuntimeError('Alice did not receive the receipt.')
            a_fx.receive(a_session, spool / back['stored'][0])
            state = a_rt.status(a_session, item['id'])['state']
            if state != 'released':
                raise RuntimeError(f'Alice shows {state!r}, not released.')
            say("4. Bob's signed receipt came back and Alice's copy shows it delivered.")
            say('Relay check passed.')
            return True
        finally:
            for quarantine in queues:
                quarantine.close()
            for auth, _, runtime, _ in owners:
                runtime.close()
                auth.close()


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or not argv[0].startswith(('https://', 'http://127.0.0.1', 'http://localhost')):
        print('Usage: python -B -m pilot.relay_live_check https://<relay>')
        return 2
    try:
        run(argv[0])
        return 0
    except Exception as error:
        print(f'Relay check failed: {error}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
