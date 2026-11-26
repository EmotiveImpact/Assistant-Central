"""Invite links end to end: two real owners, one real loopback relay, real packets."""
import hashlib
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from pilot.auth import AuthError, LocalOwnerAuth
from pilot.crypto import canonical, fingerprint
from pilot.relay_link import (INVITE_PACKETS, LinkDenied, RelayLink, is_envelope, link_code, make_link, read_link,
                              seal_envelope, join_proof)
from pilot.runtime import PilotRuntime
from relay.acrelay.client import send_with_invite
from relay.acrelay.local import serve
from relay.acrelay.service import Relay
from relay.acrelay.store import SqlStore

PASSWORD = 'Fictional invite test password'


class Owner:
    def __init__(self, root, owner, agent, relay_url, clock):
        self.directory = Path(root) / owner
        self.auth = LocalOwnerAuth(self.directory)
        self.auth.bootstrap(owner, agent, PASSWORD)
        self.session = self.auth.login(PASSWORD)
        self.runtime = PilotRuntime(self.directory, self.auth)
        self.link = RelayLink(self.directory, self.auth, self.runtime, relay_url, clock=clock)
        self.fingerprint = fingerprint(self.auth.public_identity())

    def close(self):
        self.link.close(); self.runtime.close(); self.auth.close()

    def sync(self, send=True):
        return self.link.sync(self.session, send=send)

    def peers(self):
        return {peer['fingerprint']: peer['state'] for peer in self.runtime.exchange.peers()}

    def links(self):
        return {entry['peer_id']: entry['state'] for entry in self.link.snapshot(self.session)['links']}


class RelayLinkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='parlu-link-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.offset = 0
        self.store = SqlStore.sqlite(str(self.root / 'relay.db'))
        self.relay = Relay(self.store, clock=self.clock)
        self.server = serve(self.relay)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': 0.01})
        self.thread.start()
        self.addCleanup(self.stop_relay)
        self.url = f'http://127.0.0.1:{self.server.server_port}'
        self.owners = []
        self.edem = self.owner('edem', 'Juniper')
        self.maya = self.owner('maya', 'Otto')

    def clock(self):
        return time.time() + self.offset

    def owner(self, name, agent):
        owner = Owner(self.root, name, agent, self.url, self.clock)
        self.owners.append(owner)
        self.addCleanup(owner.close)
        return owner

    def stop_relay(self):
        if self.server is not None:
            self.server.shutdown(); self.server.server_close(); self.thread.join(); self.store.close()
            self.server = None

    def connect(self, inviter, joiner, label='For a friend'):
        invite = inviter.link.create_invite(inviter.session, label)
        self.assertTrue(invite['made'])
        review = joiner.link.open_invite(joiner.session, invite['link'])
        self.assertTrue(review['ok'])
        joined = joiner.link.accept_invite(joiner.session, invite['link'], review['review_digest'])
        self.assertEqual((joined['joined'], joined['state']), (True, 'waiting'))
        self.assertEqual(inviter.sync()['joined'], 1)
        waiting = inviter.link.snapshot(inviter.session)['joiners']
        self.assertEqual(len(waiting), 1)
        added = inviter.link.decide_joiner(inviter.session, invite['id'], waiting[0]['review_digest'], 'add')
        self.assertEqual(added, {'decided': True, 'added': True, 'peer_id': joiner.fingerprint})
        self.assertEqual(joiner.sync()['connected'], 1)
        return invite

    def propose(self, sender, recipient, title='Plan the supper club menu'):
        context = hashlib.sha256(title.encode()).hexdigest()
        item = sender.runtime.propose(sender.session, recipient.fingerprint, 'task', title,
                                      'SYNTHETIC ONLY\n\nFictional request for the invite link test.',
                                      context, 'LINK-1', time.time() + 3000)
        review = sender.runtime.review(sender.session, item['id'])
        sender.runtime.release(sender.session, item['id'], review['review_digest'])
        return item['id']

    # The link itself ---------------------------------------------------------------

    def test_link_round_trips_and_keeps_everything_after_the_hash(self):
        public = self.edem.auth.public_identity()
        link = make_link(self.url, 'a' * 64, 't' * 43, 's' * 22, public, 'Fictional label')
        self.assertTrue(link.startswith(self.url + '/invite#'))
        self.assertNotIn('?', link)
        target = read_link('  ' + link + '\n')
        self.assertEqual(target['public'], public)
        self.assertEqual(target['fingerprint'], self.edem.fingerprint)
        self.assertEqual((target['mailbox'], target['send_token'], target['join_secret'], target['label']),
                         ('a' * 64, 't' * 43, 's' * 22, 'Fictional label'))
        self.assertRegex(target['code'], r'\A[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}\Z')

    def test_changed_or_malformed_links_are_refused(self):
        public = self.edem.auth.public_identity()
        link = make_link(self.url, 'a' * 64, 't' * 43, 's' * 22, public)
        other = make_link(self.url, 'b' * 64, 't' * 43, 's' * 22, public)
        self.assertNotEqual(read_link(link)['code'], read_link(other)['code'])
        for bad in (link.replace('/invite#', '/invite?x=1#'), link.replace('/invite#', '/other#'), link[:-3],
                    link.replace('http://127.0.0.1', 'http://relay.example'), link + '=', 'not a link', '',
                    link.replace('#', '#x'), 'x' * 3000, None, 5):
            with self.subTest(bad=bad):
                with self.assertRaises(LinkDenied):
                    read_link(bad)

    def test_code_is_stable_for_one_link(self):
        fields = [2, 'a' * 64, 't' * 43, 's' * 22, '', 'edem', 'Juniper', 'k1', 'k2']
        self.assertEqual(link_code(fields), link_code(list(fields)))
        self.assertNotEqual(link_code(fields), link_code(fields[:-1] + ['k3']))

    # Joining -----------------------------------------------------------------------

    def test_invite_join_add_then_a_task_and_its_receipt_cross_the_relay(self):
        invite = self.connect(self.edem, self.maya)
        self.assertEqual(self.edem.peers(), {self.maya.fingerprint: 'active'})
        self.assertEqual(self.maya.peers(), {self.edem.fingerprint: 'active'})
        self.assertEqual(self.edem.links(), {self.maya.fingerprint: 'connected'})
        self.assertEqual(self.maya.links(), {self.edem.fingerprint: 'connected'})
        self.assertEqual(self.edem.link.snapshot(self.edem.session)['invites'], [])
        # The invite token is closed once the person is added: only the fresh tokens work now.
        target = read_link(invite['link'])
        with self.assertRaises(Exception):
            send_with_invite({'relay_url': target['relay_url'], 'mailbox': target['mailbox'],
                              'send_token': target['send_token']}, b'late')

        item = self.propose(self.edem, self.maya)
        self.assertEqual(self.edem.link.snapshot(self.edem.session)['waiting_to_send'], 1)
        # A sync that was not asked to send leaves the released packet where it is.
        self.assertEqual(self.edem.sync(send=False)['sent'], 0)
        self.assertEqual(self.maya.sync()['received'], 0)
        sent = self.edem.sync(send=True)
        self.assertEqual((sent['sent'], sent['waiting_to_send']), (1, 0))
        # Posting again does not send the same packet twice.
        self.assertEqual(self.edem.sync(send=True)['sent'], 0)
        got = self.maya.sync(send=False)
        self.assertEqual((got['received'], got['receipts_sent']), (1, 1))
        status = self.maya.runtime.status(self.maya.session, item)
        self.assertEqual((status['state'], status['direction']), ('pending', 'incoming'))
        # Joining and delivery accepted nothing: the decision is still Maya's to make.
        self.assertFalse(status['authorises_execution'])
        self.edem.sync(send=False)
        outbox = self.edem.runtime.exchange.outbox_status('proposal-' + item)
        self.assertEqual(outbox['state'], 'received')

        review = self.maya.runtime.review(self.maya.session, item)
        self.maya.runtime.decide(self.maya.session, item, review['review_digest'], 'accept')
        self.assertEqual(self.maya.sync(send=True)['sent'], 1)
        self.edem.sync(send=False)
        self.assertEqual(self.edem.runtime.status(self.edem.session, item)['state'], 'accepted')

    def test_nothing_is_added_on_the_inviting_side_until_the_owner_decides(self):
        invite = self.edem.link.create_invite(self.edem.session, 'Maya')
        review = self.maya.link.open_invite(self.maya.session, invite['link'])
        self.assertEqual(review['inviter'], {'owner_id': 'edem', 'agent_id': 'Juniper',
                                             'fingerprint': self.edem.fingerprint})
        self.assertEqual(review['code'], invite['code'])
        self.assertFalse(review['known'])
        # Opening a link adds and sends nothing.
        self.assertEqual(self.maya.peers(), {})
        self.assertEqual(self.edem.sync()['joined'], 0)
        with self.assertRaises(LinkDenied):
            self.maya.link.accept_invite(self.maya.session, invite['link'], '0' * 64)
        self.maya.link.accept_invite(self.maya.session, invite['link'], review['review_digest'])
        self.edem.sync()
        self.assertEqual(self.edem.peers(), {})
        joiner = self.edem.link.snapshot(self.edem.session)['joiners'][0]
        self.assertEqual((joiner['owner_id'], joiner['agent_id'], joiner['fingerprint'], joiner['code']),
                         ('maya', 'Otto', self.maya.fingerprint, invite['code']))
        with self.assertRaises(LinkDenied):
            self.edem.link.decide_joiner(self.edem.session, invite['id'], '0' * 64, 'add')
        # A packet released while still waiting to be added stays put.
        self.propose(self.maya, self.edem)
        self.assertEqual(self.maya.sync(send=True)['sent'], 0)
        declined = self.edem.link.decide_joiner(self.edem.session, invite['id'], joiner['review_digest'], 'decline')
        self.assertEqual(declined, {'decided': True, 'added': False})
        self.assertEqual(self.edem.peers(), {})
        self.assertEqual(self.edem.link.snapshot(self.edem.session)['joiners'], [])
        self.assertEqual(self.maya.links(), {self.edem.fingerprint: 'waiting'})

    def test_join_without_the_secret_or_from_someone_else_is_ignored(self):
        invite = self.edem.link.create_invite(self.edem.session)
        target = read_link(invite['link'])
        where = {'relay_url': target['relay_url'], 'mailbox': target['mailbox'], 'send_token': target['send_token']}
        mallory = self.owner('mallory', 'Shade')
        client, _ = mallory.link._mailbox(mallory.session)
        # The relay sees the send token, so it could post a join. It never sees the join secret.
        body = {'public': mallory.auth.public_identity(), 'relay_url': self.url, 'mailbox': client.mailbox,
                'token': 'x' * 43, 'proof': join_proof('guessed-secret-guessed', self.edem.fingerprint,
                                                         mallory.fingerprint, client.mailbox, 'x' * 43)}
        forged = seal_envelope(mallory.auth, mallory.session, target['public'], 'join', body, time.time(),
                               name_sender=False)
        self.assertTrue(is_envelope(forged))
        send_with_invite(where, canonical(forged))
        # A join whose signature does not match the identity inside it.
        body['proof'] = join_proof(target['join_secret'], self.edem.fingerprint, self.maya.fingerprint,
                                   client.mailbox, 'x' * 43)
        body['public'] = self.maya.auth.public_identity()
        send_with_invite(where, canonical(seal_envelope(mallory.auth, mallory.session, target['public'], 'join',
                                                        body, time.time(), name_sender=False)))
        send_with_invite(where, b'{"header":{"parlu_link":1,"kind":"join"}}')
        result = self.edem.sync()
        self.assertEqual((result['joined'], result['rejected']), (0, 3))
        self.assertEqual(self.edem.link.snapshot(self.edem.session)['joiners'], [])
        self.assertEqual(self.edem.peers(), {})

    def test_one_invite_is_for_one_person(self):
        invite = self.edem.link.create_invite(self.edem.session)
        review = self.maya.link.open_invite(self.maya.session, invite['link'])
        self.maya.link.accept_invite(self.maya.session, invite['link'], review['review_digest'])
        second = self.owner('tom', 'Fig')
        review = second.link.open_invite(second.session, invite['link'])
        second.link.accept_invite(second.session, invite['link'], review['review_digest'])
        result = self.edem.sync()
        self.assertEqual((result['joined'], result['rejected']), (1, 1))
        self.assertEqual([j['owner_id'] for j in self.edem.link.snapshot(self.edem.session)['joiners']], ['maya'])

    def test_own_and_revoked_links_are_refused_before_anything_is_sent(self):
        invite = self.edem.link.create_invite(self.edem.session)
        self.assertEqual(self.edem.link.open_invite(self.edem.session, invite['link'])['reason'], 'own_invite')
        with self.assertRaises(LinkDenied):
            self.edem.link.accept_invite(self.edem.session, invite['link'], '0' * 64)
        self.assertEqual(self.edem.link.revoke_invite(self.edem.session, invite['id']),
                         {'revoked': True, 'relay': 'ok'})
        with self.assertRaises(LinkDenied):
            self.edem.link.show_invite(self.edem.session, invite['id'])
        review = self.maya.link.open_invite(self.maya.session, invite['link'])
        joined = self.maya.link.accept_invite(self.maya.session, invite['link'], review['review_digest'])
        self.assertEqual((joined['joined'], joined['reason']), (False, 'invite_closed'))
        # A refused join adds nothing on the joining side either.
        self.assertEqual((self.maya.peers(), self.maya.links()), ({}, {}))
        self.assertEqual(self.edem.sync()['joined'], 0)

    def test_expired_invite_cannot_be_joined(self):
        invite = self.edem.link.create_invite(self.edem.session, hours=1)
        self.assertEqual(self.edem.link.show_invite(self.edem.session, invite['id'])['link'], invite['link'])
        review = self.maya.link.open_invite(self.maya.session, invite['link'])
        self.offset = 3700  # The relay and both link stores now read an hour and a bit later.
        joined = self.maya.link.accept_invite(self.maya.session, invite['link'], review['review_digest'])
        self.assertEqual((joined['joined'], joined['reason']), (False, 'invite_closed'))
        self.assertEqual(self.edem.link.snapshot(self.edem.session)['invites'], [])
        with self.assertRaises(LinkDenied):
            self.edem.link.show_invite(self.edem.session, invite['id'])

    def test_unreachable_relay_changes_nothing_and_is_reported(self):
        self.connect(self.edem, self.maya)
        item = self.propose(self.edem, self.maya)
        self.stop_relay()
        result = self.edem.sync(send=True)
        self.assertEqual((result['relay'], result['sent'], result['waiting_to_send']), ('unreachable', 0, 1))
        self.assertEqual(self.edem.runtime.exchange.outbox_status('proposal-' + item)['attempts'], 0)
        made = self.edem.link.create_invite(self.edem.session)
        self.assertEqual(made, {'made': False, 'relay': 'unreachable'})
        self.assertEqual(self.edem.link.snapshot(self.edem.session)['last_sync']['relay'], 'unreachable')

    def test_forgetting_a_person_closes_their_send_token(self):
        self.connect(self.edem, self.maya)
        self.assertEqual(self.edem.link.forget_peer(self.edem.session, self.maya.fingerprint),
                         {'closed': True, 'relay': 'ok'})
        self.assertEqual(self.edem.links(), {})
        self.propose(self.maya, self.edem)
        result = self.maya.sync(send=True)
        self.assertEqual((result['sent'], result['waiting_to_send']), (0, 0))
        self.assertEqual(self.maya.links(), {self.edem.fingerprint: 'closed'})

    def test_secrets_are_sealed_at_rest_and_need_the_owner_session(self):
        invite = self.edem.link.create_invite(self.edem.session)
        target = read_link(invite['link'])
        raw = (self.edem.directory / 'relay-link.sqlite').read_bytes()
        for secret in (target['send_token'], target['join_secret']):
            self.assertNotIn(secret.encode(), raw)
        self.assertEqual((self.edem.directory / 'relay-link.sqlite').stat().st_mode & 0o777, 0o600)
        self.edem.auth.logout(self.edem.session)
        for call in (lambda: self.edem.link.snapshot(self.edem.session),
                     lambda: self.edem.link.create_invite(self.edem.session),
                     lambda: self.edem.link.sync(self.edem.session, send=True),
                     lambda: self.edem.link.show_invite(self.edem.session, invite['id'])):
            with self.assertRaises(AuthError):
                call()

    def test_invite_allows_only_a_few_packets(self):
        invite = self.edem.link.create_invite(self.edem.session)
        target = read_link(invite['link'])
        where = {'relay_url': target['relay_url'], 'mailbox': target['mailbox'], 'send_token': target['send_token']}
        for _ in range(INVITE_PACKETS):
            send_with_invite(where, json.dumps({'noise': True}).encode())
        with self.assertRaises(Exception):
            send_with_invite(where, b'one too many')
        self.assertEqual(self.edem.sync()['rejected'], INVITE_PACKETS)


if __name__ == '__main__':
    unittest.main()
