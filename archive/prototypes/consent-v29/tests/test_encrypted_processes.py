import json
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import unittest
from demo import fixture
from fixture_ipc import JsonProcess
from bound_identity import DELIVERY_DOMAIN, IdentityRegistry
from network import context_digest, digest
from owner_auth import DOMAIN

ROOT=Path(__file__).resolve().parent.parent


class EncryptedProcessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.meeting,self.agents,_=fixture()
        self.signers={};self.roots={};self.bindings={}
        for owner in self.meeting.participants:
            signer=JsonProcess('owner_fixture_process.py','--owner',owner)
            self.signers[owner]=signer;self.roots[owner]=signer.read()['public_key']
        self.worker=JsonProcess('encrypted_executor_process.py','--state-directory',self.tmp.name)
        self.bootstrap=self.worker.request({'owner_roots':self.roots})
        self.assertTrue(self.bootstrap['ready_for_bindings'])
        for owner,pending in self.bootstrap['requests'].items():
            result=self.signers[owner].request({'binding_request':pending,'confirmation':f'BIND {owner} {digest(pending)}'})
            self.assertTrue(result['ok']);self.bindings[owner]=result['binding']
        self.assertTrue(self.worker.request({'bindings':self.bindings})['ready'])
        self.registry=IdentityRegistry(self.meeting,self.roots,self.bindings)
        for signer in self.signers.values():
            self.assertTrue(signer.request({'registry':{'owner_roots':self.roots,'bindings':self.bindings}})['registry_verified'])

    def tearDown(self):
        self.worker.close()
        for signer in self.signers.values():signer.close()
        self.tmp.cleanup()

    def decision(self,owner,action,target,domain=DOMAIN):
        now=int(time.time())
        return {'version':1,'domain':domain,'action':action,'owner':owner,'context':context_digest(self.meeting),
                'nonce':secrets.token_hex(16),'issued_at':now,'expires_at':now+300,'target':target}

    def sign(self,owner,body,message=None):
        return self.signers[owner].request({'decision':body,'envelope':message,
            'confirmation':f"APPROVE {owner} {body['action']} {body['nonce']}"})

    def summary(self):
        result=self.worker.request({'method':'summary'})
        self.assertTrue(result['ok']);return result['result']

    def test_bootstrap_only_exchanges_public_binding_data(self):
        self.assertEqual(set(self.bootstrap),{'ready_for_bindings','requests','fixture_only'})
        for owner,pending in self.bootstrap['requests'].items():
            self.assertEqual(set(pending),{'binding','transport_proof'})
            self.assertEqual(pending['binding']['owner'],owner)
            self.assertEqual(len(pending['binding']['transport_pubkey']),64)
        self.assertEqual(self.summary()['receiver_receipts'],0)

    def test_malformed_delivery_ids_are_rejected_without_losing_live_keys(self):
        for method in ('status','dispatch','reconcile','process','lose_ack'):
            for nonce in ([],{},None,True,1,'not-a-nonce','A'*32):
                with self.subTest(method=method,nonce=nonce):
                    result=self.worker.request({'method':method,'delivery_id':nonce})
                    self.assertFalse(result['ok']);self.assertIn('Invalid encrypted delivery ID',result['error'])
        self.assertEqual(self.summary()['transitions'],0)
        self.assertTrue(self.worker.request({'method':'reopen_storage'})['ok'])

    def test_executor_refuses_key_export_signing_and_rebootstrap(self):
        for request in ({'method':'sign'},{'method':'export_key'},{'owner_roots':self.roots},
                        {'bindings':self.bindings},{'method':'control','signed':{'approved':True}}):
            with self.subTest(request=list(request)):
                result=self.worker.request(request);self.assertFalse(result['ok'])
        self.assertEqual(self.summary()['transitions'],0)

    def test_legacy_send_cannot_bypass_identity_bound_encrypted_queue(self):
        message=self.agents[1].preview_availability(self.meeting)
        body=self.decision('bob','send',{'recipient':'alice','envelope_digest':digest(message),'pair_versions':[1,1]})
        signed=self.sign('bob',body,message)['signed']
        result=self.worker.request({'method':'control','signed':signed})
        self.assertFalse(result['ok']);self.assertIn('only identity-bound encrypted sends',result['error'])

    def test_owner_signer_rejects_recipient_binding_substitution(self):
        message=self.agents[1].preview_availability(self.meeting)
        target={'recipient':'alice','envelope_digest':digest(message),'pair_versions':[1,1],
                'sender_binding':self.registry.binding_digest('bob'),'recipient_binding':self.registry.binding_digest('dana')}
        result=self.sign('bob',self.decision('bob','send',target,DELIVERY_DOMAIN),message)
        self.assertFalse(result['ok']);self.assertNotIn('signed',result)
        target['recipient_binding']=self.registry.binding_digest('alice')
        self.assertTrue(self.sign('bob',self.decision('bob','send',target,DELIVERY_DOMAIN),message)['ok'])

    def test_binding_confirmation_cannot_be_inferred_from_yes(self):
        pending=self.bootstrap['requests']['bob']
        result=self.signers['bob'].request({'binding_request':pending,'confirmation':'yes'})
        self.assertFalse(result['ok']);self.assertNotIn('binding',result)

    def test_unenrolled_signer_cannot_sign_encrypted_delivery(self):
        signer=JsonProcess('owner_fixture_process.py','--owner','bob')
        try:
            signer.read();message=self.agents[1].preview_availability(self.meeting)
            body=self.decision('bob','send',{'recipient':'alice','envelope_digest':digest(message),'pair_versions':[1,1],
                'sender_binding':self.registry.binding_digest('bob'),'recipient_binding':self.registry.binding_digest('alice')},DELIVERY_DOMAIN)
            result=signer.request({'decision':body,'envelope':message,'confirmation':f"APPROVE bob send {body['nonce']}"})
            self.assertFalse(result['ok']);self.assertIn('requires the owner-verified fixture registry',result['error'])
        finally:signer.close()

    def test_encrypted_signature_does_not_bypass_bilateral_pairing(self):
        message=self.agents[1].preview_availability(self.meeting)
        body=self.decision('bob','send',{'recipient':'alice','envelope_digest':digest(message),'pair_versions':[1,1],
            'sender_binding':self.registry.binding_digest('bob'),'recipient_binding':self.registry.binding_digest('alice')},DELIVERY_DOMAIN)
        signed=self.sign('bob',body,message)['signed']
        self.assertFalse(self.worker.request({'method':'enqueue','signed':signed,'envelope':message})['ok'])
        self.assertEqual(self.summary()['receiver_receipts'],0)


class EncryptedDemoTests(unittest.TestCase):
    def run_demo(self,*args,input=None):
        return subprocess.run([sys.executable,'encrypted_demo.py',*args],cwd=ROOT,input=input,
                              capture_output=True,text=True,timeout=20,check=True).stdout

    def test_complete_integrated_demo_has_twelve_receipts_and_transitions(self):
        output=self.run_demo('--simulate')
        self.assertIn('"agreed": true, "receiver_receipts": 12, "transitions": 12',output)
        self.assertIn('Four separate owner signers',output)

    def test_lost_ack_demo_reopens_storage_and_reconciles_without_new_attempt(self):
        output=self.run_demo('--simulate','--scenario','lost-receipt')
        self.assertIn('After storage reopen and read-only reconciliation: received ; attempts: 1',output)
        self.assertIn('"agreed": true',output)

    def test_cancel_before_dispatch_has_zero_receipts(self):
        output=self.run_demo('--simulate','--scenario','cancel-before-dispatch')
        self.assertIn('After cancellation: blocked ; attempts: 0',output)
        self.assertIn('"receiver_receipts": 0, "transitions": 0',output)

    def test_cancel_after_receipt_keeps_evidence_without_processing(self):
        output=self.run_demo('--simulate','--scenario','cancel-after-receipt')
        self.assertIn('After cancellation: received_blocked',output)
        self.assertIn('"receiver_receipts": 1, "transitions": 0',output)

    def test_manual_binding_denial_stops_before_any_message(self):
        output=self.run_demo(input='NO\n')
        self.assertIn('Exact owner binding confirmation was not supplied',output)
        self.assertNotIn('Delivery stage:',output)
        self.assertIn('Fixture processes stopped',output)

    def test_key_free_reconciliation_runs_after_preparation_process_exits(self):
        result=subprocess.run([sys.executable,'key_free_recovery_demo.py'],cwd=ROOT,capture_output=True,text=True,timeout=20,check=True)
        reports=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
        self.assertEqual(reports[0]['sender_state'],'dispatched')
        self.assertEqual(reports[1]['state'],'processed')
        self.assertEqual(reports[1]['attempts'],1)
        self.assertFalse(reports[1]['private_keys_loaded'])
        self.assertFalse(reports[1]['new_delivery_possible'])
