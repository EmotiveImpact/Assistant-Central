"""Independent real-child probes; adversary owns only its own synthetic identity."""
import copy, json, os, select, sqlite3, struct, tempfile, time, unittest
from independent_peer.fixture import PeerProcess
from independent_peer.protocol import Identity, CAPABILITY, Rejected, digest, scope, seal, open_packet, token, parse
from independent_peer.pipes import frame

class Review(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.v=PeerProcess('alice', self.tmp.name)
        self.addCleanup(self.tmp.cleanup); self.addCleanup(self.v.close)
        self.bad=Identity('bob'); self.pub=self.v.owner('describe')['descriptor']
        self.task={'id':token(),'context':digest({'fixture':'independent review'}),'capability':CAPABILITY}
        self.v.owner('configure',task=self.task,peer=self.bad.descriptor)
        self.grant=self.v.owner('allow_receive')['grant']
    def request(self):
        grant=self.bad.sign('grant',{'scope':scope(self.task,'alice','bob','request'),'nonce':token(),'epoch':1,
            'sender_binding':digest(self.pub),'recipient_binding':digest(self.bad.descriptor)})
        self.last_send_command={'op':'approve_send','operation_id':token(),'payload':'Synthetic request','grant':grant}
        sent=self.v.call('owner',self.last_send_command)
        body=open_packet(self.bad,self.pub,sent['packet'])
        proof={'scope':body['scope'],'id':body['id'],'message_digest':digest(body),'packet_digest':digest(sent['packet']),
            'grant_digest':digest(body['grant']),'processor_binding':digest(self.bad.descriptor),'status':'processed'}
        return sent,body,proof
    def result(self, sent=None, body=None, proof=None):
        return {'id':token(),'scope':scope(self.task,'bob','alice','result'),'grant':self.grant,
            'request':{'id':sent['id'] if sent else token(),'digest':digest(body) if body else '0'*64,
                       'processed':self.bad.sign('processed',proof or {})},'payload':'Synthetic malicious claim'}
    def packet(self, body): return seal(self.bad,self.pub,self.bad.sign('message',body))
    def assert_no_incoming(self): self.assertEqual(self.v.owner('inspect')['incoming'],[])
    def test_unsolicited_valid_signer_cannot_invent_local_request(self):
        with self.assertRaisesRegex(Rejected,'no locally authorized'): self.v.peer('deliver',self.packet(self.result()))
        self.assert_no_incoming()
    def test_freshly_signed_stale_grant_after_regrant(self):
        sent,body,proof=self.request(); result=self.result(sent,body,proof)
        self.v.owner('revoke_receive'); fresh=self.v.owner('allow_receive')['grant']
        with self.assertRaisesRegex(Rejected,'not current'): self.v.peer('deliver',self.packet(result))
        self.assert_no_incoming(); result['grant']=fresh
        self.v.peer('deliver',self.packet(result))
    def test_valid_signer_wrong_phase_and_context_proofs(self):
        sent,body,proof=self.request()
        for field,value in [('scope',{**proof['scope'],'context':'f'*64}),('scope',{**proof['scope'],'kind':'result'}),
                            ('status','received'),('id',token()),('processor_binding',digest(self.pub))]:
            changed={**proof,field:value}; result=self.result(sent,body,changed)
            with self.subTest(field=field,value=value), self.assertRaises(Rejected): self.v.peer('deliver',self.packet(result))
        result=self.result(sent,body,proof); result['request']['processed']=self.bad.sign('received',proof)
        with self.assertRaises(Rejected): self.v.peer('deliver',self.packet(result))
        self.assert_no_incoming()
    def test_cancel_replay_is_historical_and_changed_bytes_denied(self):
        sent,body,proof=self.request(); result=self.result(sent,body,proof); packet=self.packet(result)
        first=self.v.peer('deliver',packet); self.v.owner('cancel')
        replay=self.v.peer('deliver',packet)
        self.assertTrue(replay['historical_replay']); self.assertEqual(first['received'],replay['received']); self.assertIsNone(replay['processed'])
        with self.assertRaises(Rejected): self.v.owner('process',id=result['id'])
        with self.assertRaisesRegex(Rejected,'collision'): self.v.peer('deliver',self.packet(result))
        result['id']=token()
        with self.assertRaisesRegex(Rejected,'terminal'): self.v.peer('deliver',self.packet(result))
        self.assertEqual(self.v.owner('inspect')['processed_projection'],[])
    def test_authenticated_processing_claim_does_not_bypass_local_revocation(self):
        sent,body,proof=self.request(); result=self.result(sent,body,proof)
        self.v.owner('revoke_receive')
        self.v.peer('evidence',{'status':'processed','evidence':self.bad.sign('processed',proof)})
        with self.assertRaises(Rejected): self.v.peer('deliver',self.packet(result))
        state=self.v.owner('inspect'); self.assertTrue(state['outgoing'][0]['processed_evidence_present']); self.assertFalse(state['policy']['active']); self.assert_no_incoming()
    def test_result_commit_is_atomic_across_inbox_and_outbox_evidence(self):
        from independent_peer.fixture import UncertainOutcome
        sent,body,proof=self.request(); result=self.result(sent,body,proof)
        with sqlite3.connect(self.v.database) as db:
            db.execute("CREATE TRIGGER review_fault BEFORE UPDATE OF processed ON outbox BEGIN SELECT RAISE(ABORT, 'synthetic review abort'); END")
        with self.assertRaises(UncertainOutcome): self.v.peer('deliver',self.packet(result))
        self.v.process.wait(timeout=3)
        with sqlite3.connect(self.v.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM inbox').fetchone()[0],0)
            self.assertIsNone(db.execute('SELECT processed FROM outbox').fetchone()[0])
    def test_timeout_stops_child_and_closes_both_lanes(self):
        from independent_peer.fixture import UncertainOutcome
        sent,body,proof=self.request()
        with self.assertRaises(UncertainOutcome): self.v.call('owner',{'op':'inspect'},timeout=0)
        self.assertTrue(self.v.broken)
        self.assertIsNotNone(self.v.process.poll())
        for name in ('owner_r','owner_w','peer_r','peer_w'): self.assertIsNone(getattr(self.v,name))
        with self.assertRaisesRegex(UncertainOutcome,'poisoned'): self.v.peer('deliver',self.packet(self.result(sent,body,proof)))
        with sqlite3.connect(self.v.database) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM inbox').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM outbox').fetchone()[0],1)
    def test_cancel_blocks_packet_bearing_owner_operation_replay(self):
        sent,body,proof=self.request()
        repeated=self.v.call('owner',self.last_send_command)
        self.assertEqual(repeated['packet'],sent['packet']); self.assertTrue(repeated['historical_replay'])
        self.assertFalse(sent['historical_replay']); self.assertEqual(sent['release'],'approved_and_released')
        self.v.owner('cancel')
        with self.assertRaisesRegex(Rejected,'terminal'): self.v.call('owner',self.last_send_command)
        with self.assertRaisesRegex(Rejected,'terminal'): self.v.owner('packet',id=sent['id'])
        self.assertEqual(len(self.v.owner('inspect')['outgoing']),1)
    def test_peer_rejections_do_not_change_dispatch_lane(self):
        before=self.v.owner('inspect')
        for command in [{'op':'cancel','operation_id':token()}, {'op':'describe','value':{}},
                        {'op':'deliver','value':{},'lane':'owner'}, {'op':'evidence','value':{'status':'processed','evidence':{}}}]:
            with self.assertRaises(Rejected): self.v.call('peer',command)
        self.assertEqual(before,self.v.owner('inspect'))
        self.v.owner('revoke_receive'); self.assertFalse(self.v.owner('inspect')['policy']['active'])
    def test_partial_peer_owner_command_cannot_cross_lane_then_eof(self):
        forged=frame({'op':'cancel','operation_id':token()}); os.write(self.v.peer_w,forged[:-1])
        state=self.v.owner('inspect'); self.assertIsNone(state['policy']['terminal'])
        os.close(self.v.peer_w); self.v.peer_w=-1; self.v.process.wait(timeout=3)
        with sqlite3.connect(self.v.database) as db:
            self.assertIsNone(db.execute('SELECT terminal FROM policy').fetchone()[0])

if __name__=='__main__': unittest.main()
