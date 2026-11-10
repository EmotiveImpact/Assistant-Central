"""Synthetic cryptographic and durable transport checks; no external I/O."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey

from pilot.crypto import (MAX_PACKET, TransportDenied, b64, canonical, digest,
                          fingerprint, open_packet, packet_header, seal, unb64)
from pilot.transport import PeerExchange, MAX_ATTEMPTS


class FixtureIdentity:
    """Disposable test identities, not the production encrypted vault."""
    def __init__(self, owner, agent):
        self.signing = Ed25519PrivateKey.generate()
        self.exchange_key = X25519PrivateKey.generate()
        self.public = {'owner_id': owner, 'agent_id': agent,
                       'signing_key': b64(self.signing.public_key().public_bytes_raw()),
                       'exchange_key': b64(self.exchange_key.public_key().public_bytes_raw())}

    def public_identity(self): return dict(self.public)

    def authenticate(self, session):
        if session != 'fixture-session': raise PermissionError('Session rejected')
        return {'owner_id': self.public['owner_id'], 'agent_id': self.public['agent_id']}

    def sign(self, session, data):
        self.authenticate(session)
        return self.signing.sign(data)

    def exchange(self, session, public):
        self.authenticate(session)
        return self.exchange_key.exchange(X25519PublicKey.from_public_bytes(public))


SESSION = 'fixture-session'


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.now = 1000
        self.alice = FixtureIdentity('fictional-alice', 'writer')
        self.bob = FixtureIdentity('fictional-bob', 'reviewer')
        self.eve = FixtureIdentity('fictional-eve', 'other')
        self.paths = {name: Path(self.temp.name) / (name + '.sqlite') for name in ('a','b')}
        self.connections = []
        self.a = self.exchange('a', self.alice)
        self.b = self.exchange('b', self.bob)
        self.a.enroll_peer(self.bob.public, fingerprint(self.bob.public))
        self.b.enroll_peer(self.alice.public, fingerprint(self.alice.public))

    def tearDown(self):
        for db in self.connections:
            try: db.close()
            except sqlite3.Error: pass

    def exchange(self, name, identity):
        db = sqlite3.connect(self.paths[name], isolation_level=None, timeout=3)
        self.connections.append(db)
        return PeerExchange(db, identity.public, clock=lambda: self.now)

    def packet(self, message_id='message-one', **overrides):
        args = dict(message_id=message_id, context='context-one', artifact_id='artifact-one',
                    proposal_id='proposal-one', kind='proposal',
                    payload={'text': 'SYNTHETIC ONLY: a fictional reviewed artifact'},
                    expires=1100, now=1000)
        args.update(overrides)
        return seal(self.alice, SESSION, self.bob.public, **args)

    def delivered(self):
        packet = self.packet()
        self.a.queue(packet)
        outbound = self.a.prepare_attempt('message-one')
        result = self.b.receive(outbound, self.bob, SESSION)
        return packet, result

    def test_roundtrip_binds_exact_payload_and_direction(self):
        packet = self.packet()
        plain = open_packet(self.bob, SESSION, self.alice.public, packet, 1000)
        self.assertEqual(plain['payload']['text'], 'SYNTHETIC ONLY: a fictional reviewed artifact')
        self.assertEqual(plain['header']['sender'], fingerprint(self.alice.public))
        self.assertEqual(plain['header']['recipient'], fingerprint(self.bob.public))
        self.assertNotIn('fictional reviewed artifact', canonical(packet).decode())

    def test_per_message_ephemeral_key_and_nonce_differ(self):
        first, second = self.packet(), self.packet('message-two')
        self.assertNotEqual(first['header']['ephemeral'], second['header']['ephemeral'])
        self.assertNotEqual(first['header']['nonce'], second['header']['nonce'])
        self.assertNotEqual(first['ciphertext'], second['ciphertext'])

    def test_explicit_fingerprint_enrolment_required(self):
        with self.assertRaises(TransportDenied): self.a.enroll_peer(self.eve.public, '0' * 64)
        packet = seal(self.eve, SESSION, self.bob.public, message_id='evil', context='c', artifact_id='a',
                      proposal_id='p', kind='proposal', payload={}, expires=1100, now=1000)
        with self.assertRaises(TransportDenied): self.b.receive(packet, self.bob, SESSION)
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM peer_inbox').fetchone()[0], 0)

    def test_changed_peer_key_cannot_replace_enrolment(self):
        changed = FixtureIdentity('fictional-bob', 'reviewer')
        with self.assertRaises(TransportDenied): self.a.enroll_peer(changed.public, fingerprint(changed.public))
        self.a.revoke_peer(fingerprint(self.bob.public))
        with self.assertRaises(TransportDenied): self.a.enroll_peer(self.bob.public, fingerprint(self.bob.public))

    def test_changed_local_identity_cannot_reopen_exchange(self):
        with self.assertRaises(TransportDenied): PeerExchange(self.a.db, self.eve.public)

    def test_modified_header_or_ciphertext_signature_is_rejected(self):
        packet = self.packet()
        mutations = [('context', 'different'), ('artifact_id','different'), ('proposal_id','different'),
                     ('message_id','different'), ('kind','decision'), ('recipient',fingerprint(self.eve.public)),
                     ('sender',fingerprint(self.eve.public)), ('expires',1200)]
        for field,value in mutations:
            changed = deepcopy(packet); changed['header'][field] = value
            with self.subTest(field=field), self.assertRaises(TransportDenied):
                self.b.receive(changed, self.bob, SESSION)
        for field,size in (('ciphertext',32),('signature',64)):
            changed=deepcopy(packet); changed[field]=b64(bytes(size))
            with self.assertRaises(TransportDenied): self.b.receive(changed,self.bob,SESSION)

    def test_wrong_local_receiver_cannot_decrypt(self):
        with self.assertRaises(TransportDenied): open_packet(self.eve,SESSION,self.alice.public,self.packet(),1000)
        with self.assertRaises(TransportDenied): self.b.receive(self.packet(),self.eve,SESSION)

    def test_invalid_session_cannot_decrypt_or_obtain_cached_receipt(self):
        packet,_ = self.delivered()
        with self.assertRaises(PermissionError): self.b.receive(packet,self.bob,'wrong')
        with self.assertRaises(PermissionError): self.b.receipt_for(self.bob,'wrong','message-one')

    def test_unknown_members_and_noncanonical_encodings_rejected(self):
        packet=self.packet()
        variants=[]
        changed=deepcopy(packet);changed['extra']=True;variants.append(changed)
        changed=deepcopy(packet);changed['header']['extra']=True;variants.append(changed)
        changed=deepcopy(packet);changed['signature']+='=';variants.append(changed)
        changed=deepcopy(packet);changed['header']['nonce']='+'*16;variants.append(changed)
        changed=deepcopy(packet);changed['header']['kind']=[];variants.append(changed)
        for changed in variants:
            with self.assertRaises(TransportDenied): packet_header(changed)

    def test_packet_payload_depth_and_size_bounds(self):
        with self.assertRaises(TransportDenied): self.packet(payload={'text':'x'*20000})
        nested={}
        for _ in range(10): nested={'x':nested}
        with self.assertRaises(TransportDenied): self.packet(payload=nested)
        with self.assertRaises(TransportDenied): self.packet(payload={'value':float('nan')})
        with self.assertRaises(TransportDenied): self.packet(payload={'text':'\ud800'})
        packet=self.packet();packet['ciphertext']='x'*MAX_PACKET
        with self.assertRaises(TransportDenied): packet_header(packet)

    def test_invalid_time_and_expiry_bounds(self):
        for value in (1000,4601,True,float('inf'),float('nan'),None):
            with self.subTest(expires=value), self.assertRaises(TransportDenied): self.packet(expires=value)
        packet=self.packet()
        with self.assertRaises(TransportDenied): open_packet(self.bob,SESSION,self.alice.public,packet,1100)
        with self.assertRaises(TransportDenied): open_packet(self.bob,SESSION,self.alice.public,packet,900)

    def test_exact_duplicate_receive_returns_metadata_without_payload(self):
        packet,first=self.delivered()
        repeat=self.b.receive(packet,self.bob,SESSION)
        self.assertFalse(first['duplicate']);self.assertTrue(repeat['duplicate'])
        self.assertIsNone(repeat['envelope'])
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM peer_inbox').fetchone()[0],1)
        self.now=1200
        self.assertTrue(self.b.receive(packet,self.bob,SESSION)['duplicate'])

    def test_duplicate_message_id_with_fresh_ciphertext_is_rejected(self):
        packet,_=self.delivered()
        different=self.packet()
        self.assertNotEqual(digest(packet),digest(different))
        with self.assertRaises(TransportDenied): self.b.receive(different,self.bob,SESSION)
        with self.assertRaises(TransportDenied): self.a.queue(different)

    def test_retries_return_original_packet_only_and_are_bounded(self):
        packet=self.packet();self.a.queue(packet)
        for index in range(MAX_ATTEMPTS):
            self.assertEqual(self.a.prepare_attempt('message-one'),packet)
            self.assertEqual(self.a.outbox_status('message-one')['attempts'],index+1)
        with self.assertRaises(TransportDenied): self.a.prepare_attempt('message-one')
        self.assertEqual(self.a.pending(),[])
        self.assertEqual(self.a.outbox_status('message-one')['state'],'uncertain')

    def test_restart_preserves_original_uncertain_packet_and_duplicate_fence(self):
        packet,_=self.delivered()
        self.a.db.close();self.b.db.close()
        self.a=self.exchange('a',self.alice);self.b=self.exchange('b',self.bob)
        self.assertEqual(self.a.outbox_status('message-one')['state'],'uncertain')
        self.assertEqual(self.a.prepare_attempt('message-one'),packet)
        self.assertTrue(self.b.receive(packet,self.bob,SESSION)['duplicate'])

    def test_authenticated_receipt_binds_original_and_is_not_owner_acceptance(self):
        packet,_=self.delivered()
        receipt=self.b.receipt_for(self.bob,SESSION,'message-one')
        self.assertEqual(receipt,self.b.receipt_for(self.bob,SESSION,'message-one'))
        result=self.a.receive(receipt,self.alice,SESSION)
        self.assertEqual(result['envelope']['payload']['packet_digest'],digest(packet))
        state=self.a.outbox_status('message-one')
        self.assertEqual(state['state'],'received')
        self.assertEqual(state['owner_acceptance'],'not_established')
        self.assertEqual(state['work_execution'],'not_established')
        self.assertTrue(self.a.receive(receipt,self.alice,SESSION)['duplicate'])
        with self.assertRaises(TransportDenied): self.a.prepare_attempt('message-one')
        with self.assertRaises(TransportDenied): self.a.receipt_for(self.alice,SESSION,result['message_id'])

    def test_no_receipt_can_be_minted_for_unreceived_or_invalid_packet(self):
        with self.assertRaises(TransportDenied): self.b.receipt_for(self.bob,SESSION,'message-one')
        packet=self.packet();packet['ciphertext']=b64(bytes(32))
        with self.assertRaises(TransportDenied): self.b.receive(packet,self.bob,SESSION)
        with self.assertRaises(TransportDenied): self.b.receipt_for(self.bob,SESSION,'message-one')

    def test_forged_plain_acknowledgement_cannot_update_outbox(self):
        self.a.queue(self.packet())
        with self.assertRaises(TransportDenied): self.a.receive({'stored':True},self.alice,SESSION)
        self.assertEqual(self.a.outbox_status('message-one')['state'],'queued')

    def test_wrong_receipt_digest_direction_and_scope_rejected(self):
        packet,_=self.delivered()
        for field,value in (('packet_digest','0'*64),('message_id','unknown'),('effect','accepted')):
            payload={'message_id':'message-one','packet_digest':digest(packet),'effect':'durably_received_only'}
            payload[field]=value
            receipt=seal(self.bob,SESSION,self.alice.public,message_id='wrong-'+field,context='context-one',
                         artifact_id='artifact-one',proposal_id='proposal-one',kind='receipt',payload=payload,expires=1100,now=1000)
            with self.subTest(field=field), self.assertRaises(TransportDenied): self.a.receive(receipt,self.alice,SESSION)
        receipt=seal(self.bob,SESSION,self.alice.public,message_id='wrong-context',context='different',
                     artifact_id='artifact-one',proposal_id='proposal-one',kind='receipt',
                     payload={'message_id':'message-one','packet_digest':digest(packet),'effect':'durably_received_only'},expires=1100,now=1000)
        with self.assertRaises(TransportDenied): self.a.receive(receipt,self.alice,SESSION)
        self.assertEqual(self.a.outbox_status('message-one')['state'],'uncertain')

    def test_receipt_cannot_be_replaced_by_new_message_id(self):
        packet,_=self.delivered()
        receipt=self.b.receipt_for(self.bob,SESSION,'message-one')
        self.a.receive(receipt,self.alice,SESSION)
        alternative=seal(self.bob,SESSION,self.alice.public,message_id='alternate-receipt',context='context-one',
                         artifact_id='artifact-one',proposal_id='proposal-one',kind='receipt',
                         payload={'message_id':'message-one','packet_digest':digest(packet),'effect':'durably_received_only'},expires=1100,now=1000)
        with self.assertRaises(TransportDenied): self.a.receive(alternative,self.alice,SESSION)

    def test_out_of_order_receipt_without_original_outbox_is_denied(self):
        packet=self.packet();self.b.receive(packet,self.bob,SESSION)
        receipt=self.b.receipt_for(self.bob,SESSION,'message-one')
        with self.assertRaises(TransportDenied): self.a.receive(receipt,self.alice,SESSION)
        self.assertEqual(self.a.db.execute('SELECT COUNT(*) FROM peer_inbox').fetchone()[0],0)

    def test_cancel_stops_local_retry_but_late_receipt_remains_exposure_evidence(self):
        packet,_=self.delivered()
        self.a.cancel('message-one')
        self.assertEqual(self.a.outbox_status('message-one')['state'],'cancelled')
        self.assertEqual(self.a.queue(packet)['state'],'cancelled')
        with self.assertRaises(TransportDenied): self.a.prepare_attempt('message-one')
        self.a.receive(self.b.receipt_for(self.bob,SESSION,'message-one'),self.alice,SESSION)
        status=self.a.outbox_status('message-one')
        self.assertEqual(status['state'],'cancelled')
        self.assertIsNotNone(status['receipt_id'])

    def test_peer_revocation_blocks_queue_receive_and_retry(self):
        packet=self.packet();self.a.queue(packet)
        self.a.revoke_peer(fingerprint(self.bob.public))
        self.b.revoke_peer(fingerprint(self.alice.public))
        with self.assertRaises(TransportDenied): self.a.prepare_attempt('message-one')
        with self.assertRaises(TransportDenied): self.b.receive(packet,self.bob,SESSION)
        self.assertEqual(self.a.pending(),[])

    def test_application_and_receive_rollback_together(self):
        packet=self.packet()
        self.b.db.execute('CREATE TABLE application(id TEXT PRIMARY KEY)')
        self.b.db.execute('BEGIN IMMEDIATE')
        self.b.receive(packet,self.bob,SESSION)
        self.b.db.execute("INSERT INTO application VALUES('proposal')")
        self.b.db.execute('ROLLBACK')
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM peer_inbox').fetchone()[0],0)
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM application').fetchone()[0],0)
        self.assertFalse(self.b.receive(packet,self.bob,SESSION)['duplicate'])

    def test_receipt_and_outbox_state_rollback_together(self):
        self.delivered();receipt=self.b.receipt_for(self.bob,SESSION,'message-one')
        self.a.db.execute('BEGIN IMMEDIATE')
        self.a.receive(receipt,self.alice,SESSION)
        self.a.db.execute('ROLLBACK')
        self.assertEqual(self.a.outbox_status('message-one')['state'],'uncertain')
        self.assertEqual(self.a.db.execute('SELECT COUNT(*) FROM peer_inbox').fetchone()[0],0)

    def test_expired_original_cannot_create_first_receipt(self):
        packet=self.packet();self.a.queue(packet);self.now=1100
        with self.assertRaises(TransportDenied): self.b.receive(packet,self.bob,SESSION)
        with self.assertRaises(TransportDenied): self.a.prepare_attempt('message-one')
        self.assertEqual(self.a.pending(),[])

    def test_transport_database_stores_no_plaintext_payload(self):
        self.delivered()
        for exchange in (self.a,self.b):
            dump='\n'.join(exchange.db.iterdump())
            self.assertNotIn('fictional reviewed artifact',dump)
            self.assertNotIn('fixture-session',dump)

    def test_concurrent_duplicate_delivery_admits_once(self):
        packet=self.packet();barrier=threading.Barrier(2);results=[];errors=[]
        def worker():
            db=sqlite3.connect(self.paths['b'],isolation_level=None,timeout=3)
            try:
                exchange=PeerExchange(db,self.bob.public,clock=lambda:1000)
                barrier.wait(3)
                results.append(exchange.receive(packet,self.bob,SESSION)['duplicate'])
            except BaseException as exc:errors.append(exc)
            finally:db.close()
        threads=[threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(5)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors,[]);self.assertCountEqual(results,[True,False])

    def test_actual_owner_vault_sign_and_exchange_api_composes(self):
        from pilot.auth import LocalOwnerAuth
        auth_a=LocalOwnerAuth(Path(self.temp.name)/'owner-a',clock=lambda:1000)
        auth_b=LocalOwnerAuth(Path(self.temp.name)/'owner-b',clock=lambda:1000)
        self.addCleanup(auth_a.close);self.addCleanup(auth_b.close)
        auth_a.bootstrap('owner-a','assistant-a','Synthetic-passphrase-A')
        auth_b.bootstrap('owner-b','assistant-b','Synthetic-passphrase-B')
        session_a=auth_a.login('Synthetic-passphrase-A');session_b=auth_b.login('Synthetic-passphrase-B')
        packet=seal(auth_a,session_a,auth_b.public_identity(),message_id='vault-message',context='vault-context',
                    artifact_id='vault-artifact',proposal_id='vault-proposal',kind='proposal',
                    payload={'text':'SYNTHETIC'},expires=1100,now=1000)
        self.assertEqual(open_packet(auth_b,session_b,auth_a.public_identity(),packet,1000)['payload'],{'text':'SYNTHETIC'})


if __name__ == '__main__':unittest.main()
