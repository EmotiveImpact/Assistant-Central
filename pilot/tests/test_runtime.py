"""Separate-store adversarial runtime checks with actual signed encrypted packets."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from pilot.auth import LocalOwnerAuth, AuthError
from pilot.crypto import digest, fingerprint, seal, TransportDenied
from pilot.runtime import PilotRuntime, RuntimeDenied, RuntimeOutcomeUnknown, VERSION


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.now = 1000
        self.auths, self.runtimes, self.sessions = {}, {}, {}
        for name in ('alice','bob','mallory'):
            (self.root/name).mkdir(mode=0o700)
            auth = LocalOwnerAuth(self.root/name/'auth', clock=lambda:self.now)
            auth.bootstrap(name,name+'-assistant','correct-horse-battery-'+name)
            self.auths[name]=auth
            self.sessions[name]=auth.login('correct-horse-battery-'+name,ttl=900)
            self.runtimes[name]=PilotRuntime(self.root/name/'runtime',auth,clock=lambda:self.now)
        self.a,self.b,self.m=(self.runtimes[n] for n in ('alice','bob','mallory'))
        for sender,recipient in ((self.a,self.b),(self.b,self.a),(self.a,self.m),(self.m,self.a),(self.b,self.m),(self.m,self.b)):
            sender.enrol_peer(self.session(sender),recipient.identity,recipient.fingerprint)

    def tearDown(self):
        for runtime in self.runtimes.values():runtime.close()
        for auth in self.auths.values():auth.close()
        self.tmp.cleanup()

    def session(self,runtime):return self.sessions[runtime.identity['owner_id']]

    def propose(self, runtime=None, recipient=None, **kwargs):
        runtime=runtime or self.a;recipient=recipient or self.b
        return runtime.propose(self.session(runtime),recipient.fingerprint,
                               kwargs.pop('kind','task'),kwargs.pop('title','Synthetic task'),
                               kwargs.pop('text','SYNTHETIC ONLY: write a fictional garden introduction.'),
                               kwargs.pop('context','a'*64),kwargs.pop('task_id','garden-task'),
                               kwargs.pop('expires',1500),**kwargs)

    def release(self,runtime,item):
        session=self.session(runtime)
        review=runtime.review(session,item['id'])
        return runtime.release(session,item['id'],review['review_digest'])

    def deliver(self,sender,receiver,item):
        packet=sender.prepare_delivery(self.session(sender),item['message_id'])
        result=receiver.receive(self.session(receiver),packet)
        if result['receipt'] is not None:
            sender.receive(self.session(sender),result['receipt'])
        return result

    def accepted_task(self,provider=None):
        item=self.release(self.a,self.propose(provider_disclosure=provider))
        incoming=self.deliver(self.a,self.b,item)['item']
        result=self.b.decide(self.session(self.b),incoming['id'],
                             self.b.review(self.session(self.b),incoming['id'])['review_digest'],'accept')
        pending=self.b.state(self.session(self.b))['outbox']
        decision=next(p for p in pending if p['message_id'].startswith('decision-'))
        self.deliver(self.b,self.a,decision)
        return result

    def test_distinct_stores_only_recipient_decision_changes_recipient_state(self):
        original=self.propose();released=self.release(self.a,original)
        self.assertEqual(self.b.state(self.session(self.b))['items'],[])
        incoming=self.deliver(self.a,self.b,released)['item']
        self.assertEqual(incoming['state'],'pending')
        with self.assertRaises(RuntimeDenied):
            self.a.decide(self.session(self.a),original['id'],self.a.review(self.session(self.a),original['id'])['review_digest'],'accept')
        self.assertEqual(self.b.status(self.session(self.b),original['id'])['state'],'pending')
        self.assertEqual(self.a.status(self.session(self.a),original['id'])['state'],'released')

    def test_no_authenticated_session_can_be_replaced_by_owner_label(self):
        item=self.propose()
        for bad in ('alice','bob',self.session(self.b),'',None):
            with self.subTest(bad=bad is None),self.assertRaises(AuthError):
                self.a.release(bad,item['id'],self.a.review(self.session(self.a),item['id'])['review_digest'])

    def test_exact_acceptance_receipt_is_separate_from_transport_receipt(self):
        task=self.accepted_task()
        self.assertEqual(task['state'],'accepted')
        self.assertFalse(task['authorises_execution'])
        observed=self.a.status(self.session(self.a),task['id'])
        self.assertEqual(observed['state'],'accepted')
        self.assertEqual(observed['decision_digest'],task['decision_digest'])

    def test_duplicate_delivery_and_decisions_are_idempotent(self):
        released=self.release(self.a,self.propose())
        packet=self.a.prepare_delivery(self.session(self.a),released['message_id'])
        first=self.b.receive(self.session(self.b),packet)
        duplicate=self.b.receive(self.session(self.b),packet)
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(first['receipt'],duplicate['receipt'])
        review=self.b.review(self.session(self.b),released['id'])
        rejected=self.b.decide(self.session(self.b),released['id'],review['review_digest'],'reject')
        self.assertEqual(self.b.decide(self.session(self.b),released['id'],review['review_digest'],'reject'),rejected)
        with self.assertRaises(RuntimeDenied):self.b.decide(self.session(self.b),released['id'],review['review_digest'],'accept')
        self.assertEqual(self.b.receive(self.session(self.b),packet)['item']['state'],'rejected')

    def test_wrong_review_cannot_release_or_decide(self):
        item=self.propose()
        with self.assertRaises(RuntimeDenied):self.a.release(self.session(self.a),item['id'],'0'*64)
        incoming=self.deliver(self.a,self.b,self.release(self.a,item))['item']
        with self.assertRaises(RuntimeDenied):self.b.decide(self.session(self.b),incoming['id'],'0'*64,'accept')

    def test_owner_session_revocation_blocks_all_actions_and_reads(self):
        item=self.propose();session=self.session(self.a)
        self.a.auth.logout(session)
        for call in (lambda:self.a.state(session),lambda:self.a.review(session,item['id']),
                     lambda:self.a.release(session,item['id'],'a'*64)):
            with self.assertRaises(AuthError):call()

    def test_restart_keeps_rejected_decision_and_requires_fresh_login(self):
        item=self.release(self.a,self.propose());self.deliver(self.a,self.b,item)
        review=self.b.review(self.session(self.b),item['id'])
        self.b.decide(self.session(self.b),item['id'],review['review_digest'],'reject')
        old=self.session(self.b)
        self.b.close();self.auths['bob'].close()
        auth=LocalOwnerAuth(self.root/'bob'/'auth',clock=lambda:self.now)
        self.auths['bob']=auth
        self.b=PilotRuntime(self.root/'bob'/'runtime',auth,clock=lambda:self.now)
        self.runtimes['bob']=self.b
        with self.assertRaises(AuthError):self.b.status(old,item['id'])
        self.sessions['bob']=auth.login('correct-horse-battery-bob')
        self.assertEqual(self.b.status(self.session(self.b),item['id'])['state'],'rejected')

    def test_release_does_not_reissue_after_restart_but_retains_exact_packet_retry(self):
        item=self.release(self.a,self.propose())
        packet=self.a.prepare_delivery(self.session(self.a),item['message_id'])
        self.a.close()
        self.a=PilotRuntime(self.root/'alice'/'runtime',self.auths['alice'],clock=lambda:self.now)
        self.runtimes['alice']=self.a
        with self.assertRaises(RuntimeDenied):self.release(self.a,item)
        self.assertEqual(self.a.prepare_delivery(self.session(self.a),item['message_id']),packet)

    def test_cancel_before_delayed_proposal_creates_terminal_fence(self):
        item=self.release(self.a,self.propose())
        original=self.a.prepare_delivery(self.session(self.a),item['message_id'])
        cancelled=self.a.cancel(self.session(self.a),item['id'],self.a.review(self.session(self.a),item['id'])['review_digest'])
        cancel=next(p for p in self.a.state(self.session(self.a))['outbox'] if p['message_id'].startswith('cancel-'))
        self.deliver(self.a,self.b,cancel)
        incoming=self.b.receive(self.session(self.b),original)['item']
        self.assertEqual(incoming['state'],'cancelled')
        with self.assertRaises(RuntimeDenied):self.b.decide(self.session(self.b),item['id'],self.b.review(self.session(self.b),item['id'])['review_digest'],'accept')
        self.assertTrue(self.a.status(self.session(self.a),item['id'])['cancel_packet_receipt_observed'])

    def test_delayed_cancel_does_not_retroactively_erase_acceptance(self):
        item=self.release(self.a,self.propose());self.deliver(self.a,self.b,item)
        self.a.cancel(self.session(self.a),item['id'],self.a.review(self.session(self.a),item['id'])['review_digest'])
        accepted=self.b.decide(self.session(self.b),item['id'],self.b.review(self.session(self.b),item['id'])['review_digest'],'accept')
        self.assertEqual(accepted['state'],'accepted') # remote cancel not yet observed
        cancel=next(p for p in self.a.state(self.session(self.a))['outbox'] if p['message_id'].startswith('cancel-'))
        self.deliver(self.a,self.b,cancel)
        historical=self.b.status(self.session(self.b),item['id'])
        self.assertEqual(historical['state'],'cancelled')
        self.assertEqual(historical['historical_state'],'accepted')
        self.assertIsNone(self.b.review(self.session(self.b),item['id'])['content'])

    def test_other_enrolled_peer_cannot_cancel_someone_elses_proposal(self):
        item=self.release(self.a,self.propose());self.deliver(self.a,self.b,item)
        body=json.loads(self.a._row(item['id'])[0]['body'])
        payload={'domain':VERSION+'/cancel','item_id':item['id'],'role':'source','context':body['context'],
                 'artifact_digest':body['artifact_digest'],'route':{key:body[key] for key in ('kind','task_id','parent_id')}}
        forged=seal(self.m.auth,self.session(self.m),self.b.identity,message_id='wrong-peer-cancel',
                    context=body['context'],artifact_id=body['artifact_digest'],proposal_id=item['id'],kind='cancel',payload=payload,expires=1500,now=self.now)
        with self.assertRaises(RuntimeDenied):self.b.receive(self.session(self.b),forged)
        self.assertEqual(self.b.status(self.session(self.b),item['id'])['state'],'pending')

    def test_unverified_inherited_source_permissions_are_rejected(self):
        with self.assertRaises(RuntimeDenied):self.propose(source_permissions={'owner':'bob','upstream':['secret']})
        item=self.release(self.a,self.propose())
        body=json.loads(self.a._row(item['id'])[0]['body'])
        body['source_permissions']['upstream']=['invented-source']
        packet=seal(self.a.auth,self.session(self.a),self.b.identity,message_id='invented-lineage',
                    context=body['context'],artifact_id=body['artifact_digest'],proposal_id=digest(body),kind='proposal',payload=body,expires=1500,now=self.now)
        with self.assertRaises(RuntimeDenied):self.b.receive(self.session(self.b),packet)
        self.assertEqual(self.b.state(self.session(self.b))['items'],[])

    def test_returned_artifact_binds_exact_accepted_parent_and_origin_only(self):
        parent=self.accepted_task()
        artifact=self.propose(self.b,self.a,kind='artifact',title='Garden introduction',text='SYNTHETIC RESULT',
                              parent_id=parent['id'],context=parent['context'],task_id=parent['task_id'])
        returned=self.deliver(self.b,self.a,self.release(self.b,artifact))['item']
        self.assertEqual(returned['kind'],'artifact')
        self.assertEqual(returned['parent_id'],parent['id'])
        self.assertEqual(returned['state'],'pending')
        self.assertEqual(self.a.review(self.session(self.a),returned['id'])['source_permissions']['origin'],'task-derived-return')
        with self.assertRaises(RuntimeDenied):
            self.propose(self.b,self.m,kind='artifact',parent_id=parent['id'],context=parent['context'],task_id=parent['task_id'])

    def test_return_requires_acceptance_and_current_parent(self):
        parent=self.release(self.a,self.propose());self.deliver(self.a,self.b,parent)
        with self.assertRaises(RuntimeDenied):self.propose(self.b,self.a,kind='artifact',parent_id=parent['id'])
        self.b.decide(self.session(self.b),parent['id'],self.b.review(self.session(self.b),parent['id'])['review_digest'],'accept')
        self.b.cancel(self.session(self.b),parent['id'],self.b.review(self.session(self.b),parent['id'])['review_digest'])
        with self.assertRaises(RuntimeDenied):self.propose(self.b,self.a,kind='artifact',parent_id=parent['id'])

    def test_origin_owner_cancellation_blocks_late_return_even_if_sender_unaware(self):
        parent=self.accepted_task()
        artifact=self.release(self.b,self.propose(self.b,self.a,kind='artifact',parent_id=parent['id']))
        self.a.cancel(self.session(self.a),parent['id'],self.a.review(self.session(self.a),parent['id'])['review_digest'])
        with self.assertRaises(RuntimeDenied):self.deliver(self.b,self.a,artifact)

    def test_peer_revocation_blocks_new_release_and_acceptance(self):
        item=self.propose();self.a.revoke_peer(self.session(self.a),self.b.fingerprint)
        with self.assertRaises(TransportDenied):self.release(self.a,item)
        cancelled=self.a.cancel(self.session(self.a),item['id'],self.a.review(self.session(self.a),item['id'])['review_digest'])
        self.assertEqual(cancelled['state'],'cancelled')
        self.assertFalse(cancelled['peer_cancellation_observed'])

    def test_incoming_revoked_peer_hides_content_and_accept_action(self):
        item=self.release(self.a,self.propose());self.deliver(self.a,self.b,item)
        self.b.revoke_peer(self.session(self.b),self.a.fingerprint)
        review=self.b.review(self.session(self.b),item['id'])
        self.assertIsNone(review['content']);self.assertNotIn('accept',review['allowed_actions'])

    @contextmanager
    def lost_commit_ack(self,runtime):
        original=runtime.db
        class CommitProxy:
            def __getattr__(self,key):return getattr(original,key)
            def execute(self,sql,*args):
                result=original.execute(sql,*args)
                if sql=='COMMIT':raise sqlite3.OperationalError('SECRET acknowledgement lost')
                return result
        runtime.db=CommitProxy()
        try:yield
        finally:runtime.db=original

    def test_lost_release_commit_ack_retains_one_original_packet(self):
        item=self.propose();review=self.a.review(self.session(self.a),item['id'])
        with self.lost_commit_ack(self.a):
            with self.assertRaises(RuntimeOutcomeUnknown) as caught:
                self.a.release(self.session(self.a),item['id'],review['review_digest'])
        self.assertNotIn('SECRET',str(caught.exception))
        retained=self.a.status(self.session(self.a),item['id'])
        self.assertEqual(retained['state'],'released')
        with self.assertRaises(RuntimeDenied):self.a.release(self.session(self.a),item['id'],review['review_digest'])
        self.assertEqual(len(self.a.state(self.session(self.a))['outbox']),1)

    def test_lost_decision_commit_ack_reconciles_original_terminal_decision(self):
        item=self.release(self.a,self.propose());self.deliver(self.a,self.b,item)
        review=self.b.review(self.session(self.b),item['id'])
        with self.lost_commit_ack(self.b):
            with self.assertRaises(RuntimeOutcomeUnknown):
                self.b.decide(self.session(self.b),item['id'],review['review_digest'],'accept')
        self.assertEqual(self.b.decide(self.session(self.b),item['id'],review['review_digest'],'accept')['state'],'accepted')
        with self.assertRaises(RuntimeDenied):self.b.decide(self.session(self.b),item['id'],review['review_digest'],'reject')

    def test_expiry_blocks_acceptance_and_new_return_but_rejection_is_retained(self):
        item=self.release(self.a,self.propose());self.deliver(self.a,self.b,item)
        self.now=1500
        review=self.b.review(self.session(self.b),item['id'])
        with self.assertRaises(RuntimeDenied):self.b.decide(self.session(self.b),item['id'],review['review_digest'],'accept')
        result=self.b.decide(self.session(self.b),item['id'],review['review_digest'],'reject')
        self.assertEqual(result['historical_state'],'rejected')

    def test_logical_route_aliases_cannot_renew_rejected_or_expired_work(self):
        item=self.propose()
        self.now=1001
        with self.assertRaises(RuntimeDenied):self.propose(text='Changed text',expires=1501)
        self.assertEqual(len(self.a.state(self.session(self.a))['items']),1)

    def test_auth_expiry_rechecked_before_transaction_commit(self):
        session=self.auths['alice'].login('correct-horse-battery-alice',ttl=1)
        event=self.a._event
        def expired(*args,**kwargs):event(*args,**kwargs);self.now=1002
        with patch.object(self.a,'_event',expired):
            with self.assertRaises(AuthError):
                self.a.propose(session,self.b.fingerprint,'task','Synthetic','SYNTHETIC ONLY','b'*64,'other',1500)
        self.assertEqual(self.a.db.execute('SELECT COUNT(*) FROM runtime_items').fetchone()[0],0)

    def test_proposal_expiry_during_decision_sealing_prevents_accept_commit(self):
        item=self.release(self.a,self.propose());self.deliver(self.a,self.b,item)
        review=self.b.review(self.session(self.b),item['id'])
        packet=self.b._packet
        def expire(*args,**kwargs):
            result=packet(*args,**kwargs)
            self.now=1500
            return result
        with patch.object(self.b,'_packet',expire):
            with self.assertRaises(RuntimeDenied):
                self.b.decide(self.session(self.b),item['id'],review['review_digest'],'accept')
        self.assertEqual(self.b.status(self.session(self.b),item['id'])['historical_state'],'pending')
        self.assertEqual(self.b.state(self.session(self.b))['outbox'],[])

    def test_expiry_during_release_sealing_preserves_unreleased_draft(self):
        item=self.propose();review=self.a.review(self.session(self.a),item['id'])
        packet=self.a._packet
        def expire(*args,**kwargs):
            result=packet(*args,**kwargs);self.now=1500;return result
        with patch.object(self.a,'_packet',expire):
            with self.assertRaises((RuntimeDenied,TransportDenied)):
                self.a.release(self.session(self.a),item['id'],review['review_digest'])
        self.assertEqual(self.a.status(self.session(self.a),item['id'])['historical_state'],'draft')
        self.assertEqual(self.a.db.execute('SELECT COUNT(*) FROM peer_outbox').fetchone()[0],0)

    def test_first_receipt_signing_cannot_commit_expired_proposal(self):
        item=self.release(self.a,self.propose());packet=self.a.prepare_delivery(self.session(self.a),item['message_id'])
        receipt=self.b.exchange.receipt_for
        def expire(*args,**kwargs):
            result=receipt(*args,**kwargs);self.now=1500;return result
        with patch.object(self.b.exchange,'receipt_for',expire):
            with self.assertRaises(RuntimeDenied):self.b.receive(self.session(self.b),packet)
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM runtime_items').fetchone()[0],0)
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM peer_inbox').fetchone()[0],0)
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM peer_receipts').fetchone()[0],0)

    def test_receipt_and_runtime_admission_rollback_together(self):
        item=self.release(self.a,self.propose());packet=self.a.prepare_delivery(self.session(self.a),item['message_id'])
        with patch.object(self.b,'_event',side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):self.b.receive(self.session(self.b),packet)
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM runtime_items').fetchone()[0],0)
        self.assertEqual(self.b.db.execute('SELECT COUNT(*) FROM peer_inbox').fetchone()[0],0)
        self.assertFalse(self.b.receive(self.session(self.b),packet)['duplicate'])

    def test_no_provider_grant_is_implied_by_task_acceptance(self):
        item=self.accepted_task()
        binding={'item_id':item['id'],'context':item['context'],'payload_digest':item['artifact_digest'],
                 'provider':'openai','model':'gpt-test','max_output_tokens':64}
        with self.b._transaction(self.session(self.b)):
            with self.assertRaises(RuntimeDenied):self.b.authorise_provider(self.session(self.b),binding)

    def test_exact_signed_provider_grant_is_rechecked_against_model_and_cancel(self):
        grant={'provider':'openai','model':'gpt-test','max_output_tokens':64}
        item=self.accepted_task(grant)
        binding={'item_id':item['id'],'context':item['context'],'payload_digest':item['artifact_digest'],**grant}
        with self.b._transaction(self.session(self.b)):
            self.assertTrue(self.b.authorise_provider(self.session(self.b),binding)['synthetic_only'])
            with self.assertRaises(RuntimeDenied):self.b.authorise_provider(self.session(self.b),dict(binding,model='different'))
        self.b.cancel(self.session(self.b),item['id'],self.b.review(self.session(self.b),item['id'])['review_digest'])
        with self.b._transaction(self.session(self.b)):
            with self.assertRaises(RuntimeDenied):self.b.authorise_provider(self.session(self.b),binding)

    def test_metadata_and_audit_exclude_text_and_session_tokens(self):
        item=self.propose(text='SYNTHETIC PRIVATE TEXT')
        output=json.dumps(self.a.state(self.session(self.a)))
        self.assertNotIn('SYNTHETIC PRIVATE TEXT',output)
        self.assertNotIn(self.session(self.a),output)

    def test_concurrent_opposite_decisions_one_commit(self):
        item=self.release(self.a,self.propose());self.deliver(self.a,self.b,item)
        review=self.b.review(self.session(self.b),item['id'])['review_digest']
        barrier=threading.Barrier(2);results=[];errors=[]
        def worker(decision):
            runtime=PilotRuntime(self.root/'bob'/'runtime',self.auths['bob'],clock=lambda:self.now)
            try:
                barrier.wait(5)
                try:results.append(runtime.decide(self.session(self.b),item['id'],review,decision)['state'])
                except RuntimeDenied:results.append('denied')
            except BaseException as exc:errors.append(exc)
            finally:runtime.close()
        threads=[threading.Thread(target=worker,args=(d,)) for d in ('accept','reject')]
        for t in threads:t.start()
        for t in threads:t.join(8)
        self.assertFalse(any(t.is_alive() for t in threads));self.assertEqual(errors,[])
        self.assertEqual(results.count('denied'),1)
        self.assertEqual(self.b.db.execute("SELECT COUNT(*) FROM runtime_audit WHERE event='recipient_decided'").fetchone()[0],1)


if __name__=='__main__':unittest.main()
