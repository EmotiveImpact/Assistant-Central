"""Independent informational-proof isolation review; offline disposable keys only."""
import copy
import time
import unittest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from bound_identity import (signed_bytes, verify_owner, BINDING_DOMAIN,
                            DELIVERY_DOMAIN, POSSESSION_DOMAIN, RECEIPT_DOMAIN)
from continuity_proofs import OWNER_DOMAIN, CONTINUITY_DOMAIN, PURPOSE, verify_certificate
from fixture_ipc import JsonProcess
from generic_protocol import task_context_digest
from network import Denied, digest
from owner_auth import DOMAIN as AUTH_DOMAIN
from owner_withdrawal import DOMAIN as WITHDRAW_DOMAIN
from task_fixtures import fixture


class IndependentContinuityProofReview(unittest.TestCase):
    def setUp(self):
        self.owner = Ed25519PrivateKey.generate()
        self.anchor = Ed25519PrivateKey.generate()
        self.root = self.anchor.public_key().public_bytes_raw().hex()
        now = int(time.time())
        self.body = dict(purpose=PURPOSE, incarnation='1'*64, identity_id='anchor-one',
            identity_version=1, continuity_root=self.root,
            fingerprint=digest({'continuity_root': self.root}), association_id='assoc-one',
            selector='garden', context=task_context_digest(fixture('garden')[0]), actor='alice',
            owner_root=self.owner.public_key().public_bytes_raw().hex(), nonce='2'*64,
            generation=1, issued_at=now, review_expires_at=now+60, certificate_expires_at=now+3600)

    def certificate(self):
        return {'body':copy.deepcopy(self.body),
            'owner_signature':self.owner.sign(signed_bytes(OWNER_DOMAIN,self.body)).hex(),
            'continuity_signature':self.anchor.sign(signed_bytes(CONTINUITY_DOMAIN,self.body)).hex()}

    def test_all_signed_coordinates_are_immutable_and_workspace_specific(self):
        certificate = self.certificate()
        self.assertEqual(verify_certificate(certificate,'1'*64),certificate)
        with self.assertRaises(Denied): verify_certificate(certificate,'3'*64)
        for field, value in self.body.items():
            with self.subTest(field=field):
                altered=copy.deepcopy(certificate)
                altered['body'][field] = value+1 if type(value) is int else ('4'*64 if len(value)==64 else 'different')
                with self.assertRaises(Denied): verify_certificate(altered,'1'*64)

    def test_possession_signatures_never_validate_as_authority_or_each_other(self):
        certificate=self.certificate()
        for key,signature,own_domain in [
                (self.body['owner_root'],certificate['owner_signature'],OWNER_DOMAIN),
                (self.root,certificate['continuity_signature'],CONTINUITY_DOMAIN)]:
            for domain in (AUTH_DOMAIN,WITHDRAW_DOMAIN,BINDING_DOMAIN,DELIVERY_DOMAIN,
                           POSSESSION_DOMAIN,RECEIPT_DOMAIN,OWNER_DOMAIN,CONTINUITY_DOMAIN):
                if domain != own_domain:
                    with self.subTest(domain=domain,key=key):
                        with self.assertRaises(Denied): verify_owner(key,domain,self.body,signature)

    def test_historical_verifier_does_not_assert_current_validity(self):
        self.body.update(issued_at=1,review_expires_at=60,certificate_expires_at=100)
        certificate=self.certificate()
        result=verify_certificate(certificate,'1'*64)
        self.assertEqual(set(result), {'body','owner_signature','continuity_signature'})
        self.assertLess(result['body']['certificate_expires_at'],int(time.time()))
        result['body']['actor']='bob'
        self.assertEqual(certificate['body']['actor'],'alice')

    def test_closed_certificate_schema_and_strict_scalars(self):
        for field, bad in [('identity_version',True),('generation',1.0),('issued_at',False),
                           ('certificate_expires_at',2**54),('actor',[]),('purpose','authority'),
                           ('fingerprint','A'*64),('continuity_root',self.body['owner_root'])]:
            altered=self.certificate(); altered['body'][field]=bad
            with self.subTest(field=field):
                with self.assertRaises(Denied):verify_certificate(altered,'1'*64)
        for added in ('private_key','binding','grant','owner_signature_domain'):
            certificate=self.certificate(); certificate[added]='extra'
            with self.assertRaises(Denied):verify_certificate(certificate,'1'*64)
        certificate=self.certificate(); certificate['body']['authority']='send'
        with self.assertRaises(Denied):verify_certificate(certificate,'1'*64)

    def owner_process(self, continuity=True):
        args=('--continuity-incarnation','1'*64,'--continuity-selector','garden') if continuity else ()
        child=JsonProcess('owner_fixture_process.py','--owner','alice','--workflow','generic','--task-fixture','garden',*args)
        self.addCleanup(child.close)
        self.body['owner_root']=child.read()['public_key']
        return child

    def request(self,body=None):
        body=copy.deepcopy(body or self.body)
        anchor={k:body[k] for k in ('incarnation','identity_id','identity_version','continuity_root','fingerprint')}
        return {'continuity_proof':body,'anchor':anchor,'confirmation':'ASSOCIATE '+digest(body)}

    def test_owner_process_rejects_wrong_scope_without_consuming_valid_request(self):
        child=self.owner_process()
        for field,value in [('actor','bob'),('owner_root','5'*64),('incarnation','6'*64),
                            ('selector','astronomy'),('context','7'*64)]:
            body=copy.deepcopy(self.body); body[field]=value
            self.assertFalse(child.request(self.request(body))['ok'],field)
        result=child.request(self.request())
        self.assertTrue(result['ok'])
        verify_owner(self.body['owner_root'],OWNER_DOMAIN,self.body,result['signature'])
        self.assertFalse(child.request(self.request())['ok'])

    def test_unenrolled_task_signer_cannot_sign_continuity(self):
        child=self.owner_process(False)
        self.assertFalse(child.request(self.request())['ok'])

    def test_anchor_process_rejects_task_control_and_duplicate_association(self):
        child=JsonProcess('continuity_fixture_process.py','--incarnation','1'*64,'--identity-id','anchor-one')
        self.addCleanup(child.close)
        root=child.read()['public_key']; self.body.update(continuity_root=root,fingerprint=digest({'continuity_root':root}))
        self.assertFalse(child.request({'decision':{},'envelope':None,'confirmation':'APPROVE alice pair x'})['ok'])
        request=self.request(); request.pop('anchor')
        result=child.request(request); self.assertTrue(result['ok'])
        verify_owner(root,CONTINUITY_DOMAIN,self.body,result['signature'])
        self.assertFalse(child.request(request)['ok'])



class IndependentContinuityWorkspaceReview(unittest.TestCase):
    def setUp(self):
        from owner_workspace import OwnerWorkspace
        self.w=OwnerWorkspace(continuity=True)
        self.addCleanup(self.w.close)
        self.context=task_context_digest(fixture('garden')[0])

    def commit(self,operation,review):
        return self.w.continuity_commit(operation,review,operation.upper()+' CONTINUITY '+review['review_digest'])

    def enroll(self):
        return self.commit('enroll',self.w.continuity_preview({'operation':'enroll','identity_id':'anchor-one'}))

    def preview(self,aid='assoc-one'):
        return self.w.continuity_preview({'operation':'associate','identity_id':'anchor-one',
            'association_id':aid,'selector':'garden','context':self.context,'actor':'alice'})

    def setup_task(self):
        self.enroll(); self.w.create('garden',self.context)

    def test_preview_creates_no_children_and_no_state(self):
        from unittest.mock import patch
        before=self.w.continuity_state()
        with patch('continuity_workspace.JsonProcess') as child:
            self.w.continuity_preview({'operation':'enroll','identity_id':'anchor-one'})
            child.assert_not_called()
        self.assertEqual(before,self.w.continuity_state())
        self.assertEqual(self.w._slots,{})

    def test_retire_only_removes_recognition_not_task_keys_or_processes(self):
        self.setup_task()
        row=self.commit('associate',self.preview())
        self.assertTrue(row['active'])
        service=self.w._slots['garden']['service']
        roots=dict(service.roots); pid=service.executor.process.pid
        self.commit('retire',self.w.continuity_preview({'operation':'retire','identity_id':'anchor-one'}))
        state=self.w.continuity_state()
        self.assertEqual(state['associations'][0]['status'],'retired')
        self.assertEqual(service.roots,roots); self.assertEqual(service.executor.process.pid,pid)
        self.assertIsNone(service.executor.process.poll()); self.assertFalse(service.closed)
        self.assertEqual(service.bindings,{})
        verify_certificate(state['associations'][0]['certificate'],state['incarnation'])

    def test_lost_second_signature_consumes_association_without_retry(self):
        from unittest.mock import patch
        self.setup_task(); review=self.preview()
        signer=self.w._continuity.identities['anchor-one']['signer']
        with patch.object(signer,'request',side_effect=RuntimeError('lost response')) as request:
            with self.assertRaisesRegex(RuntimeError,'lost response'):self.commit('associate',review)
            replay=self.commit('associate',review)
            self.assertEqual(request.call_count,1)
        self.assertEqual(replay['status'],'uncertain')
        self.assertIsNone(replay['certificate']); self.assertFalse(replay['active'])
        with self.assertRaises(Denied):self.preview()

    def test_closed_task_denies_previously_reviewed_new_association(self):
        self.setup_task(); review=self.preview()
        self.w.close_task('garden',self.context)
        with self.assertRaises(Denied):self.commit('associate',review)
        self.assertEqual(self.w.continuity_state()['associations'],[])

    def test_certificate_expiry_is_independent_of_review_expiry(self):
        from unittest.mock import patch
        self.setup_task(); review=self.preview(); self.commit('associate',review)
        b=review['body']
        with patch('continuity_workspace.time.time',return_value=b['review_expires_at']):
            self.assertTrue(self.w.continuity_state()['associations'][0]['active'])
        with patch('continuity_workspace.time.time',return_value=b['certificate_expires_at']):
            row=self.w.continuity_state()['associations'][0]
            self.assertFalse(row['active']); self.assertEqual(row['status'],'expired')
            verify_certificate(row['certificate'],self.w.continuity_state()['incarnation'])

    def test_history_can_reach_declared_capacity_and_remains_exportable(self):
        from continuity_proofs import MAX_ASSOCIATIONS
        self.setup_task()
        for i in range(MAX_ASSOCIATIONS):self.commit('associate',self.preview('assoc-'+str(i)))
        state=self.w.continuity_state()
        self.assertEqual(len(state['associations']),MAX_ASSOCIATIONS)
        self.commit('retire',self.w.continuity_preview({'operation':'retire','identity_id':'anchor-one'}))
        self.assertTrue(all(not r['active'] for r in self.w.continuity_state()['associations']))
        with self.assertRaises(Denied):self.preview('assoc-extra')

    def test_recomputed_modified_review_cannot_obtain_signatures(self):
        from continuity_proofs import review as make_review
        self.setup_task(); original=self.preview()
        body=copy.deepcopy(original['body']); body['certificate_expires_at']-=1
        forged=make_review(body)
        with self.assertRaises(Denied):self.commit('associate',forged)
        self.assertEqual(self.w.continuity_state()['associations'],[])
        self.assertTrue(self.commit('associate',original)['active'])

    def test_relationship_stop_fences_proof_but_not_historical_verification(self):
        self.setup_task(); proven=self.commit('associate',self.preview())
        pending=self.preview('assoc-pending')
        group=self.w.relationship_preview({'operation':'create','spec':{'group_id':'group-one',
            'label':'Fixture group','members':[{'selector':'garden','context':self.context}]}})
        self.w.relationship_commit('create',group,'CREATE GROUP')
        stop=self.w.relationship_preview({'operation':'stop','group_id':'group-one'})
        self.w.relationship_commit('stop',stop,'STOP GROUP')
        with self.assertRaises(Denied):self.commit('associate',pending)
        state=self.w.continuity_state()
        self.assertEqual(state['associations'][0]['status'],'stopped')
        verify_certificate(proven['certificate'],state['incarnation'])

    def test_restricted_agent_schema_and_inbox_disclose_no_continuity_anchor(self):
        import json
        from test_restricted_host_protocol import init,wire
        self.setup_task(); self.commit('associate',self.preview())
        service=self.w._slots['garden']['service']
        for owner, request in service.requests.items():
            self.w.action('garden',self.context,{'action':'bind','owner':owner,
                'binding_digest':digest(request),'confirmation':'BIND '+owner})
        session=self.w.adapter('garden',self.context,'alice')
        self.addCleanup(session.close)
        payloads=[init(session),json.loads(session.handle(wire('tools/list','list'))),
            json.loads(session.handle(wire('tools/call','inbox',name='inbox',arguments={})))]
        serialized=json.dumps(payloads)
        anchor=self.w.continuity_state()['identities'][0]['anchor']
        for secret in (anchor['continuity_root'],anchor['fingerprint'],anchor['incarnation'],'anchor-one','assoc-one'):
            self.assertNotIn(secret,serialized)
        response=json.loads(session.handle(wire('tools/call','forbidden',name='continuity_state',arguments={})))
        self.assertTrue('error' in response or response['result']['isError'])

    def test_late_second_signature_never_activates_and_cannot_be_renewed(self):
        from unittest.mock import patch
        self.setup_task(); review=self.preview()
        signer=self.w._continuity.identities['anchor-one']['signer']
        original=signer.request
        with patch('continuity_workspace.time.time',return_value=review['body']['issued_at']) as clock:
            def late(request):
                result=original(request)
                clock.return_value=review['body']['review_expires_at']
                return result
            with patch.object(signer,'request',side_effect=late) as request:
                with self.assertRaises(Denied):self.commit('associate',review)
                row=self.commit('associate',review)
                self.assertEqual(request.call_count,1)
        self.assertEqual(row['status'],'uncertain'); self.assertIsNone(row['certificate'])

    def test_exact_historical_replay_after_workspace_close_never_signs_again(self):
        from unittest.mock import patch
        self.setup_task(); review=self.preview(); self.commit('associate',review)
        signer=self.w._continuity.identities['anchor-one']['signer']
        self.w.close()
        with patch.object(signer,'request',side_effect=AssertionError('must not sign')):
            row=self.commit('associate',review)
        self.assertFalse(row['active']); self.assertIsNotNone(row['certificate'])

    def test_signer_exit_does_not_claim_fresh_possession_or_renew_certificate(self):
        self.setup_task(); proven=self.commit('associate',self.preview())
        signer=self.w._continuity.identities['anchor-one']['signer']
        signer.close()
        state=self.w.continuity_state()
        self.assertEqual(state['associations'][0]['certificate'],proven['certificate'])
        with self.assertRaises(RuntimeError):self.commit('associate',self.preview('assoc-two'))
        state=self.w.continuity_state()
        self.assertEqual(state['associations'][1]['status'],'uncertain')
        self.assertEqual(len(state['identities']),1)


if __name__=='__main__': unittest.main()
