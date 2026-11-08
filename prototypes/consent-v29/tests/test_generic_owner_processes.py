"""Real subprocess tests: no signing keys enter this test/service parent."""
import copy
import unittest
from generic_demo import fixture
from network import Denied, digest
from owner_ui_service import OwnerUIService


class GenericOwnerProcessesTests(unittest.TestCase):
    def setUp(self):
        self.service = OwnerUIService('generic')
        self.addCleanup(self.service.close)
        for owner, pending in self.service.requests.items():
            self.service.action({'action':'bind','owner':owner,'binding_digest':digest(pending),'confirmation':'BIND '+owner})

    def next(self):
        return self.service.action({'action':'next'})

    def resolve(self, card, choice='approve'):
        fields={'action':choice,'owner':card['owner'],'request_id':card['request_id'],'review_digest':card['review_digest']}
        if choice=='approve': fields['confirmation']='APPROVE '+card['owner']
        return self.service.action(fields)['card']

    def submit(self, card):
        return self.service.action({'action':'submit','owner':card['owner'],'request_id':card['request_id']})['card']

    def request_card(self):
        for _ in range(2):
            card=self.next()['card']
            self.assertEqual(card['action'],'pair')
            self.submit(self.resolve(card))
        card=self.next()['card']
        self.assertEqual(card['envelope']['type'],'request')
        return card

    def command(self, method, card=None, **fields):
        if card: fields.update(owner=card['owner'],request_id=card['request_id'])
        return self.service._command(method,**fields)

    def test_exact_exchange_and_explicit_boundaries(self):
        card=self.request_card()
        self.assertEqual(set(self.service.roots),{'alice','bob'})
        self.assertEqual(self.service.requests['alice']['binding']['receive_from'],['bob'])
        self.assertEqual(self.service.requests['bob']['binding']['receive_from'],['alice'])
        for kind in ('request','result'):
            self.assertEqual(card['envelope']['type'],kind)
            self.assertIn('Untrusted inert payload',card['review'])
            self.assertNotIn('meeting',card['envelope'])
            card=self.resolve(card)
            self.assertEqual(card['state'],'authorized')
            self.assertEqual(self.command('summary')['receiver_receipts'],0 if kind=='request' else 1)
            self.submit(card)
            self.assertEqual(self.command('delivery_view',card)['attempts'],0)
            self.command('delivery_attempt',card)
            self.assertEqual(self.command('delivery_view',card)['state'],'received')
            self.assertEqual(self.command('summary')['transitions'],0 if kind=='request' else 1)
            self.command('delivery_process',card)
            step=self.next()
            if kind=='request':card=step['card']
        self.assertEqual(step['kind'],'complete')
        self.assertEqual(self.command('summary'),{'task_state':'completed','transitions':2,'receiver_receipts':2,'executed_tools':0,'live_provider_calls':0})

    def test_malformed_binding_frames_are_nonfatal(self):
        signer=self.service.signers['alice']
        for body in (None, [], 'invalid', 7, {}):
            pending={'binding':body,'transport_proof':'invalid'}
            response=signer.request({'binding_request':pending,'confirmation':'BIND alice '+digest(pending)})
            self.assertFalse(response['ok'])
        pending=self.service.requests['alice']
        response=signer.request({'binding_request':pending,'confirmation':'BIND alice '+digest(pending)})
        self.assertTrue(response['ok'])

    def test_wrong_owner_and_unsigned_approval(self):
        card=self.next()['card']
        with self.assertRaises(Denied):self.service.review('bob',card['request_id'])
        with self.assertRaises(Denied):self.service.state('charlie')
        with self.assertRaises(Denied):self.command('request_resolve',card,review_digest=card['review_digest'],choice='approve')
        response=self.service.signers['bob'].request({'decision':card['decision'],'envelope':None,'confirmation':f"APPROVE bob pair {card['request_id']}"})
        self.assertFalse(response['ok'])

    def test_signer_rejects_wrong_scope_and_control_peer(self):
        card=self.next()['card']
        for change in ('context','peer','cancel'):
            d=copy.deepcopy(card['decision'])
            if change=='context':d['context']='0'*64
            elif change=='peer':d['target']['peer']='charlie'
            else:d.update(action='cancel',target={'meeting':'other-task'})
            result=self.service.signers['alice'].request({'decision':d,'envelope':None,'confirmation':f"APPROVE alice {d['action']} {d['nonce']}"})
            self.assertFalse(result['ok'],change)

    def test_raw_bypasses_rejected(self):
        for method in ('control','enqueue','dispatch','process','approve','sign','owner_pair','owner_approve','lose_ack'):
            result=self.service.executor.request({'method':method})
            self.assertFalse(result['ok'],method)
            self.assertIn('bypass',result['error'])

    def test_defer_invalidates_review_and_decline_is_retained(self):
        card=self.request_card();deferred=self.resolve(card,'defer')
        self.assertEqual(deferred['state'],'deferred')
        self.assertNotEqual(card['review_digest'],deferred['review_digest'])
        with self.assertRaises(Denied):self.resolve(card)
        self.assertEqual(self.next()['card']['request_id'],card['request_id'])
        declined=self.resolve(deferred,'decline')
        self.command('reopen_storage')
        self.assertEqual(self.next()['card']['state'],'declined')
        with self.assertRaises(Denied):self.submit(declined)
        self.assertEqual(self.command('summary')['receiver_receipts'],0)

    def test_lost_ack_reopen_checks_receipt_without_retry(self):
        card=self.resolve(self.request_card());self.submit(card)
        self.assertEqual(self.command('fixture_lose_ack',card)['state'],'dispatched')
        self.command('reopen_storage')
        self.assertEqual(self.command('delivery_view',card)['attempts'],1)
        recovered=self.command('delivery_check',card)
        self.assertEqual(recovered['state'],'received');self.assertEqual(recovered['attempts'],1)
        self.command('delivery_process',card)
        self.assertEqual(self.next()['card']['owner'],'bob')

    def test_uncertain_no_receipt_cannot_withdraw_replace_or_process(self):
        card=self.resolve(self.request_card());self.submit(card)
        self.command('fixture_fail_before_receipt',card);self.command('reopen_storage')
        status=self.command('delivery_check',card)
        self.assertEqual(status['state'],'dispatched');self.assertEqual(status['attempts'],1)
        for method,extra in (('delivery_process',{}),('withdrawal_prepare',{'review_digest':card['review_digest']}),('request_replace',{'review_digest':card['review_digest']})):
            with self.assertRaises(Denied):self.command(method,card,**extra)
        self.assertEqual(self.command('summary')['receiver_receipts'],0)

    def test_signed_withdrawal_fence_survives_reopen_fresh_needs_approval(self):
        card=self.resolve(self.request_card())
        withdrawn=self.service.action({'action':'withdraw_unused','owner':card['owner'],'request_id':card['request_id'],'review_digest':card['review_digest'],'confirmation':'WITHDRAW '+card['owner']})['card']
        self.assertEqual(withdrawn['state'],'withdrawn')
        self.command('reopen_storage')
        with self.assertRaises(Denied):self.submit(card)
        fresh=self.service.action({'action':'fresh_after_withdrawal','owner':card['owner'],'request_id':card['request_id'],'review_digest':withdrawn['review_digest'],'confirmation':'REVIEW '+card['owner']})['card']
        self.assertEqual(fresh['state'],'pending');self.assertNotEqual(fresh['request_id'],card['request_id'])
        with self.assertRaises(Denied):self.submit(fresh)
        self.assertEqual(self.command('summary')['receiver_receipts'],0)

    def test_malformed_generic_or_legacy_envelope_cannot_prepare(self):
        card=self.request_card()
        envelope=card['envelope']
        mutations=[]
        e=copy.deepcopy(envelope);e['context']='0'*64;mutations.append(e)
        e=copy.deepcopy(envelope);e['version']=999;mutations.append(e)
        e=copy.deepcopy(envelope);e['recipient']='charlie';mutations.append(e)
        e=copy.deepcopy(envelope);e['payload']['execute']='browse';mutations.append(e)
        from demo import fixture as meeting_fixture
        scope,actors,_=meeting_fixture();mutations.append(actors[0].preview_availability(scope))
        for e in mutations:
            with self.assertRaises(Denied):self.command('request_prepare',owner='alice',action='send',envelope=e)

    def test_signer_independently_rejects_payload_and_confirmation_mutations(self):
        card=self.request_card()
        for mutation in ('payload','schema','context','confirmation'):
            d=copy.deepcopy(card['decision']);e=copy.deepcopy(card['envelope'])
            phrase=f"APPROVE alice send {d['nonce']}"
            if mutation=='payload':e['payload']['execute']='browse'
            elif mutation=='schema':e['version']=999
            elif mutation=='context':e['context']='0'*64
            else:phrase='APPROVE alice'
            d['target']['envelope_digest']=digest(e)
            response=self.service.signers['alice'].request({'decision':d,'envelope':e,'confirmation':phrase})
            self.assertFalse(response['ok'],mutation)

    def test_result_cannot_precede_request(self):
        card=self.request_card()
        _,_,_,result=fixture()
        with self.assertRaises(Denied):self.command('request_prepare',owner='bob',action='send',envelope=result)
        self.assertEqual(self.command('summary')['transitions'],0)

    def test_cancel_uses_explicit_legacy_scope_alias(self):
        card=self.command('request_prepare',owner='alice',action='cancel')
        self.assertEqual(card['decision']['target'],{'meeting':fixture()[0].id})
        self.assertIn('compatibility alias',card['review'])
        self.submit(self.resolve(card))
        self.assertEqual(self.next()['kind'],'stopped')
        self.assertEqual(self.command('summary')['task_state'],'cancelled')


class GenericConsoleTests(unittest.TestCase):
    def test_console_scenarios(self):
        import subprocess
        import sys
        from fixture_ipc import ROOT
        for scenario in ('normal','decline','defer','lost-receipt','uncertain'):
            with self.subTest(scenario=scenario):
                result=subprocess.run([sys.executable,str(ROOT/'owner_console.py'),'--workflow','generic','--simulate','--scenario',scenario],capture_output=True,text=True,timeout=20)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn('Final summary:',result.stdout)
                expected='completed' if scenario in ('normal','defer','lost-receipt') else 'created'
                self.assertIn('"task_state": "'+expected+'"',result.stdout)
                if scenario=='uncertain':self.assertIn('No automatic retry',result.stdout)
                if scenario=='decline':self.assertIn('will not replace it or ask again',result.stdout)

    def test_normal_mode_quit_at_binding_never_autoapproves(self):
        import subprocess
        import sys
        from fixture_ipc import ROOT
        result=subprocess.run([sys.executable,str(ROOT/'owner_console.py'),'--workflow','generic'],input='quit\n',capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('Stopped safely',result.stdout)
        self.assertNotIn('Owner signature saved',result.stdout)
        self.assertNotIn('SIMULATED choices',result.stdout)


if __name__=='__main__':unittest.main()
