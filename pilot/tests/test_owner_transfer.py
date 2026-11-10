"""Owner transfers, exact review replay fences and responsive in-flight controls."""
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from pilot.auth import LocalOwnerAuth
from pilot.crypto import canonical, digest
from pilot.https_exchange import HTTPSOutcomeUnknown
from pilot.owner_transfer import OwnerTransfer, TransferConfig, VERSION, load_config
from pilot.runtime import PilotRuntime, RuntimeDenied
from pilot.server import PilotHTTPServer
from pilot.tests import test_file_exchange as file_tests


def config(peer, quarantine=None):
    value = {'version': VERSION, 'connections': [{'id': 'reviewed-peer', 'label': 'Fictional peer',
             'peer_fingerprint': peer, 'destination': 'https://mailbox.invalid/v1/quarantine'}]}
    if quarantine is not None:
        value['quarantine_directory'] = str(quarantine)
    return TransferConfig(value)


class OwnerTransferTests(unittest.TestCase):
    def setUp(self):
        file_tests.FileExchangeTests.setUp(self)
        self.first = OwnerTransfer(self.a[2], config(self.b[2].fingerprint, self.root))
        self.second = OwnerTransfer(self.b[2], config(self.a[2].fingerprint, self.root))

    def tearDown(self):
        self.first.close(); self.second.close()
        file_tests.FileExchangeTests.tearDown(self)

    def review(self):
        return self.first.review(self.a[1], 'reviewed-peer', 'outbox', self.message_id)

    def send(self, review=None, retry=False):
        review = review or self.review()
        return self.first.send(self.a[1], 'reviewed-peer', 'outbox', self.message_id, review['review_digest'], retry)

    def wait(self):
        try: self.first.future.result(timeout=5)
        except HTTPSOutcomeUnknown: pass

    def test_disabled_by_default_and_read_only_inspection_does_not_mint(self):
        disabled = OwnerTransfer(self.a[2]); self.addCleanup(disabled.close)
        before = self.a[2].db.total_changes
        value = disabled.snapshot(self.a[1])
        self.assertFalse(value['enabled']); self.assertEqual(value['connections'], [])
        self.assertEqual(self.a[2].db.total_changes, before)
        with self.assertRaises(RuntimeDenied): disabled.review(self.a[1], 'reviewed-peer', 'outbox', self.message_id)
        self.assertFalse(self.a[2].db.execute("SELECT 1 FROM sqlite_master WHERE name='https_send_attempts'").fetchone())
        with self.assertRaises(RuntimeDenied): self.first.review(self.a[1], 'reviewed-peer', 'receipt', 'missing')
        self.assertEqual(self.a[2].db.execute('SELECT COUNT(*) FROM peer_receipts').fetchone()[0], 0)

    def test_snapshot_includes_stopped_and_received_outbox_without_packet_or_secrets(self):
        self.a[2].exchange.cancel(self.message_id)
        state = self.first.snapshot(self.a[1])
        self.assertEqual(state['outbox'][0]['state'], 'cancelled')
        self.assertEqual(self.review()['allowed_actions'], [])
        raw = json.dumps(state)
        for secret in ('SYNTHETIC PRIVATE TEXT', 'fictional-password', 'ciphertext', 'ca_file', 'quarantine_directory'):
            self.assertNotIn(secret, raw)
        self.assertNotIn(self.a[1], raw)

    def test_original_bytes_one_attempt_and_stale_review_replay_is_denied(self):
        reviewed = self.review()
        original = self.a[2].exchange._outbox(self.message_id)['packet'].encode()
        with patch('pilot.https_exchange.send_file', side_effect=lambda path,*a,**kw: (self.assertEqual(Path(path).read_bytes(), original) or {'transport_acknowledged': True})):
            self.send(reviewed); self.wait()
        state = self.first.snapshot(self.a[1])
        self.assertEqual(state['dispatch']['state'], 'finished')
        self.assertEqual(state['outbox'][0]['state'], 'uncertain')
        with self.assertRaises(RuntimeDenied): self.send(reviewed)
        retry = self.review()
        self.assertEqual(retry['allowed_actions'], ['retry'])
        with self.assertRaises(RuntimeDenied): self.send(retry)
        with patch('pilot.https_exchange.send_file', return_value={'transport_acknowledged': True}):
            self.send(retry, retry=True); self.wait()
        with self.assertRaises(RuntimeDenied): self.send(retry, retry=True)
        self.assertEqual(self.review()['outbox']['attempts'], 2)
        self.assertEqual([a['state'] for a in self.review()['attempts']], ['uncertain', 'uncertain'])
        self.assertEqual(list(self.a[2].directory.glob('.https-send-*')), [])

    def test_busy_send_rejected_without_queued_attempt_and_cancellation_is_not_overwritten(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def slow(*args, **kwargs):
            entered.set(); release.wait(5)
            return {'transport_acknowledged': True}
        with patch('pilot.https_exchange.send_file', side_effect=slow):
            self.send(); self.assertTrue(entered.wait(2))
            review = self.review()
            with self.assertRaises(RuntimeDenied): self.send(review, retry=True)
            self.assertEqual(self.first.snapshot(self.a[1])['outbox'][0]['attempts'], 1)
            self.a[2].cancel(self.a[1], self.item_id, self.a[2].review(self.a[1], self.item_id)['review_digest'])
            self.assertEqual(self.first.snapshot(self.a[1])['dispatch']['state'], 'in_flight')
            self.a[0].logout(self.a[1])
            release.set(); self.wait()
        token = self.a[0].login('fictional-password-alice')
        state = self.first.snapshot(token)
        row = next(row for row in state['outbox'] if row['message_id'] == self.message_id)
        self.assertEqual(row['state'], 'cancelled')
        self.assertEqual(row['attempts'], 1)

    def test_unknown_network_result_stays_uncertain_and_requires_fresh_explicit_retry(self):
        with patch('pilot.https_exchange.send_file', side_effect=OSError('SECRET response must not leak')):
            self.send(); self.wait()
        state = self.first.snapshot(self.a[1])
        self.assertEqual(state['dispatch']['state'], 'outcome_unknown')
        self.assertNotIn('SECRET', json.dumps(state))
        self.assertEqual(state['outbox'][0]['attempts'], 1)
        self.assertEqual(list(self.a[2].directory.glob('.https-send-*')), [])

    def test_prepared_capability_is_one_shot_and_close_abandons_without_reset(self):
        p = self.first.exchange._prepare_send(self.a[1], self.message_id,
            'https://mailbox.invalid/v1/quarantine', self.b[2].fingerprint, retry=False, ca_file=None, receipt=False)
        with patch('pilot.https_exchange.send_file', return_value={'transport_acknowledged': True}) as send:
            p.dispatch()
            with self.assertRaises(RuntimeDenied): p.dispatch()
            self.assertEqual(send.call_count, 1)
        p = self.first.exchange._prepare_send(self.a[1], self.message_id,
            'https://mailbox.invalid/v1/quarantine', self.b[2].fingerprint, retry=True, ca_file=None, receipt=False)
        p.close()
        with self.assertRaises(RuntimeDenied): p.dispatch()
        self.assertEqual(list(self.a[2].directory.glob('.https-send-*')), [])
        self.assertEqual(self.review()['outbox']['attempts'], 2)

    def test_prepared_start_window_and_original_expiry_fail_closed(self):
        for expired in (False, True):
            p = self.first.exchange._prepare_send(self.a[1], self.message_id,
                'https://mailbox.invalid/v1/quarantine', self.b[2].fingerprint, retry=expired, ca_file=None, receipt=False)
            if expired:
                self.now = 1600
            else:
                p._start_deadline = 0
            with patch('pilot.https_exchange.send_file') as sender:
                with self.assertRaises(HTTPSOutcomeUnknown): p.dispatch()
                sender.assert_not_called()
            with self.assertRaises(RuntimeDenied): p.dispatch()
            self.assertEqual(list(self.a[2].directory.glob('.https-send-*')), [])
        self.assertEqual(self.a[2].exchange.outbox_status(self.message_id)['attempts'], 2)

    def test_prepared_clock_rollback_cannot_start_a_transfer(self):
        p = self.first.exchange._prepare_send(self.a[1], self.message_id,
            'https://mailbox.invalid/v1/quarantine', self.b[2].fingerprint, retry=False, ca_file=None, receipt=False)
        self.now -= 1
        with patch('pilot.https_exchange.send_file') as sender:
            with self.assertRaises(HTTPSOutcomeUnknown): p.dispatch()
            sender.assert_not_called()
        self.assertEqual(self.a[2].exchange.outbox_status(self.message_id)['attempts'], 1)

    def test_worker_submission_failure_keeps_attempt_and_cleans_staging(self):
        with patch.object(self.first.worker, 'submit', side_effect=RuntimeError('worker unavailable')):
            with self.assertRaises(RuntimeError): self.send()
        self.assertEqual(self.review()['outbox']['attempts'], 1)
        self.assertEqual(list(self.a[2].directory.glob('.https-send-*')), [])

    def test_submit_can_start_then_raise_without_losing_in_flight_slot(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        thread = None
        def network(*args, **kwargs):
            entered.set(); release.wait(5); return {'transport_acknowledged': True}
        def uncertain_submit(operation):
            nonlocal thread
            thread = threading.Thread(target=operation)
            thread.start()
            self.assertTrue(entered.wait(2))
            raise RuntimeError('Interrupted after dispatch started')
        with patch('pilot.https_exchange.send_file', side_effect=network), patch.object(self.first.worker, 'submit', side_effect=uncertain_submit):
            with self.assertRaises(RuntimeError): self.send()
            self.assertIsNone(self.first.future)
            self.assertTrue(self.first.active())
            self.assertEqual(self.first.snapshot(self.a[1])['dispatch']['state'], 'in_flight')
            with self.assertRaises(RuntimeDenied): self.send(self.review(), retry=True)
            self.a[2].cancel(self.a[1], self.item_id, self.a[2].review(self.a[1], self.item_id)['review_digest'])
            release.set(); thread.join(timeout=2)
        self.assertFalse(self.first.active())
        row = self.a[2].exchange.outbox_status(self.message_id)
        self.assertEqual((row['attempts'], row['state']), (1, 'cancelled'))
        self.assertEqual(list(self.a[2].directory.glob('.https-send-*')), [])

    def test_selected_import_is_separate_from_receipt_and_owner_acceptance(self):
        packet = self.a[2].prepare_delivery(self.a[1], self.message_id)
        raw = canonical(packet); selected = hashlib.sha256(raw).hexdigest()
        path = self.root / (selected + '.json'); path.write_bytes(raw); path.chmod(0o600)
        before = self.b[2].db.total_changes
        review = self.second.review(self.b[1], 'reviewed-peer', 'quarantine', selected)
        self.assertFalse(review['authenticated']); self.assertEqual(self.b[2].db.total_changes, before)
        result = self.second.receive(self.b[1], 'reviewed-peer', selected, review['review_digest'])
        self.assertEqual(result['owner_acceptance'], 'not_established')
        self.assertEqual(self.b[2].status(self.b[1], self.item_id)['state'], 'pending')
        self.assertIsNone(self.second.future)
        receipt = self.second.snapshot(self.b[1])['receipts'][0]
        self.assertEqual(receipt['incoming_id'], self.message_id)
        repeat = self.second.receive(self.b[1], 'reviewed-peer', selected, review['review_digest'])
        self.assertTrue(repeat['duplicate'])
        self.assertEqual(self.second.snapshot(self.b[1])['receipts'][0], receipt)
        r = self.second.review(self.b[1], 'reviewed-peer', 'receipt', self.message_id)
        self.assertEqual(r['allowed_actions'], ['send'])
        self.assertTrue(path.exists())

    def test_quarantine_path_traversal_symlink_tamper_and_wrong_sender_fail_closed(self):
        packet = self.a[2].prepare_delivery(self.a[1], self.message_id)
        raw = canonical(packet); key = hashlib.sha256(raw).hexdigest()
        path = self.root / (key + '.json')
        for name in ('../escape', 'a'*64 + '/secret', 'not-a-digest'):
            with self.assertRaises((ValueError, PermissionError)):
                self.second.review(self.b[1], 'reviewed-peer', 'quarantine', name)
        path.symlink_to('/etc/passwd')
        with self.assertRaises((ValueError, PermissionError, OSError)):
            self.second.review(self.b[1], 'reviewed-peer', 'quarantine', key)
        path.unlink(); path.write_bytes(raw+b' '); path.chmod(0o600)
        with self.assertRaises(RuntimeDenied): self.second.review(self.b[1], 'reviewed-peer', 'quarantine', key)
        path.write_bytes(raw)
        with self.assertRaises(RuntimeDenied): self.first.review(self.a[1], 'reviewed-peer', 'quarantine', key)
        self.assertEqual(self.b[2].state(self.b[1])['items'], [])

    def test_config_is_private_bounded_strict_and_never_accepts_url_credentials(self):
        value = {'version': VERSION, 'connections': [{'id': 'test', 'label': 'Test', 'peer_fingerprint': self.b[2].fingerprint, 'destination': 'https://mailbox.invalid/v1/quarantine'}]}
        path = self.root/'config.json'; path.write_text(json.dumps(value)); path.chmod(0o600)
        self.assertEqual(load_config(path).public('test')['id'], 'test')
        path.chmod(0o644)
        with self.assertRaises(ValueError): load_config(path)
        for target in ('http://mailbox.invalid/v1/quarantine', 'https://user:secret@mailbox.invalid/v1/quarantine', 'https://mailbox.invalid/v1/quarantine?token=secret'):
            bad=copy.deepcopy(value); bad['connections'][0]['destination']=target
            with self.assertRaises(ValueError): TransferConfig(bad)
        for extra in ('password', 'token', 'automatic_send'):
            with self.assertRaises(ValueError): TransferConfig({**value, extra: 'forbidden'})


class TransferHTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        owners=[]
        for name in ('alice','bob'):
            auth=LocalOwnerAuth(self.root/name); auth.bootstrap(name,name+'-assistant','fictional-password-'+name)
            token=auth.login('fictional-password-'+name); runtime=PilotRuntime(self.root/name,auth)
            owners.append((auth,token,runtime))
        a,b=owners; self.peer=b[2].fingerprint; self.own=a[2].fingerprint
        a[2].enrol_peer(a[1],b[2].identity,self.peer)
        item=a[2].propose(a[1],self.peer,'task','Fictional transfer','SYNTHETIC ONLY','b'*64,'http-transfer',time.time()+300)
        self.item=item['id']; self.message=a[2].release(a[1],self.item,a[2].review(a[1],self.item)['review_digest'])['message_id']
        for auth,token,runtime in owners: runtime.close(); auth.close()
        self.server=PilotHTTPServer(self.root/'alice',transfer_config=config(self.peer,self.root))
        self.thread=threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':0.01}); self.thread.start()
        self.addCleanup(self.cleanup)
        self.token=self.request('POST','/api/session',{'password':'fictional-password-alice'},token='')[1]['token']
        self.base='/api/transfers/reviewed-peer/outbox/'+self.message

    def cleanup(self):
        self.server.shutdown(); self.thread.join(); self.server.server_close()

    def request(self,method,path,body=None,token=None,origin=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        headers={}
        if token is None: token=getattr(self,'token','')
        if token: headers['Authorization']='Bearer '+token
        if body is not None: headers['Content-Type']='application/json'
        if origin: headers['Origin']=origin
        try:
            connection.request(method,path,None if body is None else json.dumps(body),headers)
            response=connection.getresponse();return response.status,json.loads(response.read())
        finally: connection.close()

    def test_routes_require_session_origin_and_exact_fields(self):
        self.assertEqual(self.request('GET',self.base,token='')[0],401)
        self.assertEqual(self.request('GET',self.base,origin='https://other.invalid')[0],400)
        review=self.request('GET',self.base)[1]
        for field in ('destination','recipient','ca_file','input','quarantine_directory','packet','allow_live'):
            self.assertEqual(self.request('POST',self.base+'/send',{'review_digest':review['review_digest'],'retry':False,field:'forbidden'})[0],400)
        self.assertEqual(self.request('GET','/api/state')[1]['transfers']['outbox'][0]['attempts'],0)

    def test_network_does_not_block_status_cancel_or_logout_and_duplicate_is_not_queued(self):
        entered,release=threading.Event(),threading.Event();self.addCleanup(release.set)
        def slow(*args,**kwargs): entered.set();release.wait(4);return {'transport_acknowledged':True}
        with patch('pilot.https_exchange.send_file',side_effect=slow):
            review=self.request('GET',self.base)[1]
            status,value=self.request('POST',self.base+'/send',{'review_digest':review['review_digest'],'retry':False})
            self.assertEqual(status,200);self.assertTrue(entered.wait(2))
            self.assertTrue(value['dispatch_started'])
            state=self.request('GET','/api/state')[1]
            self.assertEqual(state['transfers']['dispatch']['state'],'in_flight')
            r=self.request('GET',self.base)[1]
            self.assertEqual(self.request('POST',self.base+'/send',{'review_digest':r['review_digest'],'retry':True})[0],400)
            item=self.request('GET','/api/items/'+self.item+'/review')[1]
            self.assertEqual(self.request('POST','/api/items/'+self.item+'/cancel',{'review_digest':item['review_digest']})[0],200)
            self.assertEqual(self.request('DELETE','/api/session',{})[0],200)
            release.set();self.server.owner.transfers.future.result(timeout=3)
        self.token=self.request('POST','/api/session',{'password':'fictional-password-alice'},token='')[1]['token']
        r=self.request('GET',self.base)[1]
        self.assertEqual(r['outbox']['state'],'cancelled');self.assertEqual(r['outbox']['attempts'],1)
        self.assertEqual(r['attempts'][0]['state'],'uncertain');self.assertEqual(r['allowed_actions'],[])

    def test_get_review_and_refresh_never_dispatch(self):
        with patch('pilot.https_exchange.send_file') as sender:
            for _ in range(3):
                self.assertEqual(self.request('GET',self.base)[0],200)
                self.assertEqual(self.request('GET','/api/state')[0],200)
            sender.assert_not_called()


class TransferTLSRoundTripTests(unittest.TestCase):
    """Facade sends original bytes through real TLS, then imports receipts separately."""
    def setUp(self):
        from pilot.tests import test_https_exchange as https_tests
        self._fixture = https_tests.HTTPSExchangeTests()
        self._fixture.setUp()
        self.addCleanup(self._fixture.tearDown)

    def test_real_tls_quarantine_import_receipt_and_acceptance_are_separate(self):
        f = self._fixture
        facades = []
        for index, owner in enumerate(f.owners):
            peer = f.owners[1-index][2]
            cfg = TransferConfig({'version': VERSION, 'connections': [{'id': 'peer', 'label': 'Fictional TLS peer',
                'peer_fingerprint': peer.fingerprint, 'destination': f.targets[1-index], 'ca_file': str(f.ca)}],
                'quarantine_directory': str(f.spools[index])})
            facade = OwnerTransfer(owner[2], cfg); facades.append(facade); self.addCleanup(facade.close)
        a,b=facades
        review=a.review(f.a[1], 'peer', 'outbox', f.message_id)
        a.send(f.a[1], 'peer', 'outbox', f.message_id, review['review_digest'], False)
        result=a.future.result(timeout=5)
        self.assertTrue(result['transport_acknowledged'])
        self.assertEqual(f.b[2].state(f.b[1])['items'], [])
        selected=b.snapshot(f.b[1])['quarantine'][0]
        reviewed=b.review(f.b[1], 'peer', 'quarantine', selected)
        b.receive(f.b[1], 'peer', selected, reviewed['review_digest'])
        self.assertEqual(f.b[2].status(f.b[1], f.item_id)['state'], 'pending')
        self.assertIsNone(b.future)
        receipt=b.review(f.b[1], 'peer', 'receipt', f.message_id)
        b.send(f.b[1], 'peer', 'receipt', f.message_id, receipt['review_digest'], False)
        b.future.result(timeout=5)
        selected=a.snapshot(f.a[1])['quarantine'][0]
        reviewed=a.review(f.a[1], 'peer', 'quarantine', selected)
        a.receive(f.a[1], 'peer', selected, reviewed['review_digest'])
        final=a.review(f.a[1], 'peer', 'outbox', f.message_id)
        self.assertEqual(final['outbox']['state'], 'received')
        self.assertEqual(final['attempts'][0]['state'], 'uncertain')
        self.assertEqual(final['allowed_actions'], [])
        self.assertEqual(f.a[2].status(f.a[1], f.item_id)['state'], 'released')
        self.assertFalse(a.snapshot(f.a[1])['authorises_execution'])
