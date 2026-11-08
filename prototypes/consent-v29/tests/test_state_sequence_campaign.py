"""Bounded seeded offline campaigns. Each seed is a distinct ordered scenario."""
import copy
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from bound_identity import signed_bytes
from durable import LocalDelivery
from encrypted_delivery import DurableEncryptedOutbox, OfflineReceiver
from generic_capabilities import BOUNDED_TEXT
from generic_owner_workflow import GenericOwnerWorkflow
from generic_protocol import task_envelope
from generic_session import GenericPersistentSession
from integrated_fixture import FixtureAuthorities
from owner_auth import SignedOwnerGateway
from agent_proposals import AgentProposalBoundary
from network import Denied, digest, canonical
from task_composer import composed_fixture


class Harness:
    def __init__(self, root, index, text=False, requester='alice'):
        self.now = [1000]
        self.path = root / str(index)
        self.path.mkdir()
        self.spec = dict(selector='custom-'+str(index), task_id='task-'+str(index),
                         conversation_id='conversation-'+str(index), requester=requester,
                         query='Fictional inert question '+str(index), max_items=2)
        if text:
            del self.spec['max_items']
            self.spec.update(capability=BOUNDED_TEXT, max_reply_chars=8)
        self.task, self.actors, self.request, _ = composed_fixture(self.spec)
        self.payload = {'text':'inert 😀'} if text else {'items':[]}
        self.result = task_envelope(self.task,'result',self.payload,digest(self.request))
        self.auth = FixtureAuthorities(self.task,1000)
        self.open()
        self.receiver_stores = []
        self.receivers = {}
        for owner in self.task.participants:
            store = LocalDelivery(self.path/(owner+'.sqlite3'),clock=lambda:self.now[0])
            self.receiver_stores.append(store)
            self.receivers[owner] = OfflineReceiver(store,self.auth.registry,owner,self.auth.transport_keys[owner])
    def open(self):
        self.store = LocalDelivery(self.path/'sender.sqlite3',clock=lambda:self.now[0])
        self.session = GenericPersistentSession(self.store,self.actors,self.task)
        self.gateway = SignedOwnerGateway(self.session,self.auth.owner_roots)
        self.box = DurableEncryptedOutbox(self.gateway,self.auth.registry,self.auth.transport_keys)
        self.flow = GenericOwnerWorkflow(self.gateway,self.box)
        self.flow.composed_spec = copy.deepcopy(self.spec)
        self.boundaries = {o:AgentProposalBoundary(self.flow,o) for o in self.task.participants}
    def reopen(self):
        self.store.close(); self.open()
    def close(self):
        self.store.close()
        for store in self.receiver_stores:store.close()
    def sign(self, card):
        d=card['decision']
        return {'decision':copy.deepcopy(d),'signature':self.auth.owner_keys[d['owner']].sign(signed_bytes(d['domain'],d)).hex()}
    def approve(self, card):
        return self.flow.resolve(card['owner'],card['request_id'],card['review_digest'],'approve',self.sign(card))
    def submit(self, card):
        self.approve(card); return self.flow.submit(card['owner'],card['request_id'])
    def deliver(self, card):
        self.submit(card); self.box.dispatch(card['request_id'],self.receivers[card['envelope']['recipient']]);self.box.process_received(card['request_id'])
    def ready(self):
        self.auth.pair_all(self.gateway,self.now[0])
        card=self.flow.prepare(self.task.requester,'send',envelope=self.request)
        self.deliver(card)
    def response(self, payload=None):
        return self.flow.preview_response(self.task.responder,digest(self.request),self.payload if payload is None else payload)
    def prepare_response(self,p):
        return self.flow.prepare_response(self.task.responder,p['request_digest'],p['envelope']['payload'],p['preview_digest'],'REVIEW RESPONSE '+self.task.responder)
    def snapshot(self):
        return {r[0]:[tuple(v) for v in self.store.db.execute('SELECT * FROM '+r[0])] for r in self.store.db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}


class StateSequenceCampaign(unittest.TestCase):
    def fixtures(self, label):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        fixtures=[Harness(Path(tmp.name),label+str(i), bool(i//2),('alice','bob')[i%2]) for i in range(4)]
        for h in fixtures:self.addCleanup(h.close)
        return fixtures

    def test_corrupted_scope_blocks_response_disclosure_and_authoring(self):
        for h in self.fixtures('scope'):
            h.ready();p=h.response();card=h.prepare_response(p)
            for corruption in ('changed','missing'):
                if corruption=='changed':h.store.db.execute('UPDATE sessions SET context=?',('0'*64,))
                else:h.store.db.execute('DELETE FROM sessions')
                before=h.snapshot()
                for operation in (lambda:h.flow.response_context(h.task.responder),lambda:h.response(),lambda:h.prepare_response(p),lambda:h.boundaries[h.task.responder].dispatch({'method':'inbox'}),lambda:h.session.view()):
                    with self.subTest(capability=h.task.capability,owner=h.task.requester,corruption=corruption),self.assertRaises(Denied):operation()
                    self.assertEqual(h.snapshot(),before)
                h.store.db.execute('INSERT OR REPLACE INTO sessions VALUES (?,?)',(h.task.id,h.session.context))
                self.assertEqual(h.prepare_response(p)['request_id'],card['request_id'])

    def assert_views(self,h,expected):
        before=h.snapshot()
        for owner in h.task.participants:
            view=h.flow.received_messages(owner)
            self.assertEqual([m['envelope'] for m in view['messages']], [e for e in expected if e['recipient']==owner])
            def keys(value):
                if isinstance(value,dict):
                    for k,v in value.items():
                        self.assertNotIn(k,{'signature','private_key','request_id','nonce','owner_roots','authorization','decision'})
                        keys(v)
                elif isinstance(value,list):
                    for v in value:keys(v)
            keys(view)
            view['messages'].clear()
        self.assertEqual(before,h.snapshot())

    def test_seeded_interleaved_lifecycle_mutations(self):
        # Four different ordered schedules; 4 scopes x 5 phases x 24 probes.
        # Every phase includes each probe family once before random selection.
        from collections import Counter
        counts=Counter()
        for seed in (918273,271828,314159,161803):
            rng=random.Random(seed);hs=self.fixtures('s'+str(seed));expected={h:[] for h in hs};cards={}
            for h in hs:h.auth.pair_all(h.gateway,h.now[0]);cards[h]=h.flow.prepare(h.task.requester,'send',envelope=h.request)
            for phase in range(5):
                schedule=[(h,i) for h in hs for i in range(24)];rng.shuffle(schedule)
                for h,i in schedule:
                    other=rng.choice([x for x in hs if x is not h]);kind=i if i<12 else rng.randrange(12)
                    counts['scheduled']+=1
                    counts['reopened' if kind==1 else 'read' if kind==0 or (kind==11 and phase==4) else 'refused']+=1
                    before={x: x.snapshot() for x in hs}
                    if kind==0:
                        self.assert_views(h,expected[h])
                    elif kind==1:
                        h.reopen()
                    elif kind==2:
                        with self.assertRaises(Denied):h.flow.response_context(h.task.requester)
                    elif kind==3:
                        with self.assertRaises(Denied):h.flow.preview_response(h.task.responder,'0'*64,h.payload)
                    elif kind==4:
                        with self.assertRaises(Denied):h.flow.preview_response(h.task.responder,digest(h.request),{'text':'x'} if 'items' in h.payload else {'items':[]})
                    elif kind==5:
                        with self.assertRaises(Denied):h.flow.review(other.task.responder,cards[other]['request_id'])
                    elif kind==6:
                        bad=copy.deepcopy(h.result);bad[rng.choice(['context','reply_to'])]='0'*64
                        with self.assertRaises(Denied):h.boundaries[h.task.responder].dispatch({'method':'propose','proposal_id':'invalid','envelope':bad})
                    elif kind==7:
                        with self.assertRaises(Denied):h.boundaries[h.task.requester].dispatch({'method':'response_context'})
                    elif kind==8:
                        bad=copy.deepcopy(h.result);bad['payload']['authorization']='approve'
                        with self.assertRaises(Denied):h.boundaries[h.task.responder].dispatch({'method':'propose','proposal_id':'invalid','envelope':bad})
                    elif kind==9:
                        with self.assertRaises(Denied):h.flow.resolve(cards[h]['owner'],cards[h]['request_id'],'0'*64,'approve',h.sign(cards[h]))
                    elif kind==10:
                        bad=copy.deepcopy(h.result);bad['sender']=h.task.requester
                        with self.assertRaises(Denied):h.boundaries[h.task.responder].dispatch({'method':'propose','proposal_id':'invalid','envelope':bad})
                    else:
                        if phase<4:
                            with self.assertRaises(Denied):h.flow.response_context(h.task.responder)
                        else:
                            view=h.flow.response_context(h.task.responder);view['incoming_request']['payload'].clear()
                    self.assertEqual(before,{x:x.snapshot() for x in hs},(seed,phase,kind))
                for h in rng.sample(hs,len(hs)):
                    if phase==0:h.approve(cards[h])
                    elif phase==1:h.flow.submit(cards[h]['owner'],cards[h]['request_id'])
                    elif phase==2:h.box.dispatch(cards[h]['request_id'],h.receivers[h.task.responder])
                    elif phase==3:h.box.process_received(cards[h]['request_id']);expected[h].append(h.request)
                    else:
                        p=h.response();card=h.prepare_response(p);h.deliver(card);expected[h].append(h.result)
                    self.assert_views(h,expected[h])
            for h in hs:
                self.assertEqual(h.session.view().state,'completed')
                with self.assertRaises(Denied):h.response()
                h.reopen();self.assert_views(h,expected[h])

        print('SEQUENCE_PROBES',dict(sorted(counts.items())))

    def test_seeded_history_failure_and_terminal_schedules(self):
        from owner_withdrawal import withdrawal_bytes
        # Eight distinct scenarios, each run for both capabilities/directions.
        for scenario in range(8):
            seed=73000+scenario;rng=random.Random(seed);hs=self.fixtures('h'+str(scenario))
            for h in rng.sample(hs,len(hs)):
                h.ready();p=h.response();card=h.prepare_response(p)
                # Aliases must share the original durable history even across reopen.
                boundary=h.boundaries[h.task.responder]
                aliases=['alias-'+str(i) for i in range(4)];rng.shuffle(aliases)
                for alias in aliases:
                    boundary.dispatch({'method':'propose','proposal_id':alias,'envelope':p['envelope']})
                    self.assertEqual(boundary.prepare_owner_review(alias)['request_id'],card['request_id'])
                if scenario==0:
                    for choice in ('defer','defer','decline'):
                        card=h.flow.resolve(card['owner'],card['request_id'],card['review_digest'],choice)
                        self.assertEqual(h.prepare_response(p)['request_id'],card['request_id'])
                    with self.assertRaises(Denied):h.flow.submit(card['owner'],card['request_id'])
                elif scenario==1:
                    h.now[0]+=301
                    old=h.prepare_response(p);self.assertEqual(old['state'],'expired')
                    with self.assertRaises(Denied):h.approve(old)
                    fresh=h.flow.replace_review(old['owner'],old['request_id'],old['review_digest'])
                    self.assertNotEqual(fresh['request_id'],old['request_id']);self.assertEqual(h.prepare_response(p)['request_id'],old['request_id'])
                    h.deliver(fresh)
                elif scenario==2:
                    h.gateway.apply(h.auth.control(h.task.requester,'revoke',{'peer':h.task.responder,'contact_version':1},h.now[0]))
                    self.assertEqual(h.prepare_response(p)['state'],'stale')
                    with self.assertRaises(Denied):h.approve(card)
                elif scenario==3:
                    h.approve(card);current=h.prepare_response(p)
                    challenge=h.flow.prepare_withdrawal(current['owner'],current['request_id'],current['review_digest'])['withdrawal']
                    signed={'withdrawal':challenge,'signature':h.auth.owner_keys[current['owner']].sign(withdrawal_bytes(challenge)).hex()}
                    h.flow.withdraw(signed);self.assertEqual(h.prepare_response(p)['state'],'withdrawn')
                    with self.assertRaises(Denied):h.flow.submit(current['owner'],current['request_id'])
                elif scenario in (4,5):
                    h.submit(card);receiver=h.receivers[h.task.requester]
                    class Failure:
                        owner,registry=receiver.owner,receiver.registry
                        def receipt(self,nonce):return receiver.receipt(nonce)
                        def receive(self,packet):
                            if scenario==4:receiver.receive(packet)
                            raise ConnectionError('injected failure '+str(scenario))
                    with self.assertRaises(ConnectionError):h.box.dispatch(card['request_id'],Failure())
                    self.assert_views(h,[h.request]);h.reopen()
                    h.box.reconcile(card['request_id'],receiver)
                    self.assert_views(h,[h.request]);self.assertEqual(h.box.status(card['request_id'])['attempts'],1)
                    if scenario==4:h.box.process_received(card['request_id'])
                    else:
                        h.gateway.apply(h.auth.control(h.task.requester,'cancel',{'meeting':h.task.id},h.now[0]))
                        h.box.reconcile(card['request_id'],receiver)
                        self.assert_views(h,[h.request]);self.assertEqual(h.box.status(card['request_id'])['attempts'],1)
                elif scenario==6:
                    h.submit(card);h.box.dispatch(card['request_id'],h.receivers[h.task.requester])
                    h.gateway.apply(h.auth.control(h.task.requester,'cancel',{'meeting':h.task.id},h.now[0]))
                    self.assertEqual(h.box.process_received(card['request_id'])['state'],'received_blocked')
                    self.assert_views(h,[h.request])
                    with self.assertRaises(Denied):h.response()
                else:
                    before=h.snapshot()
                    real_card=h.flow._card;calls=[0]
                    def fail_second(row):
                        calls[0]+=1
                        if calls[0]==2:raise RuntimeError('injected post-write failure')
                        return real_card(row)
                    with patch.object(h.flow,'_card',side_effect=fail_second):
                        with self.assertRaises(RuntimeError):h.flow.resolve(card['owner'],card['request_id'],card['review_digest'],'defer')
                    self.assertEqual(h.snapshot(),before)
                    # Fail after _insert_draft wrote a new response, not before.
                    payload={'text':'new'} if 'text' in h.payload else {'items':[{'title':'new','url':'https://example.invalid','summary':'inert'}]}
                    other=h.response(payload)
                    with patch.object(h.flow,'_card',side_effect=RuntimeError('injected post-insert failure')):
                        with self.assertRaises(RuntimeError):h.prepare_response(other)
                    self.assertEqual(h.snapshot(),before)
                    h.deliver(card)
                h.reopen()
                self.assertEqual(h.prepare_response(p)['request_id'],card['request_id'])
                for alias in aliases:self.assertEqual(h.boundaries[h.task.responder].prepare_owner_review(alias)['request_id'],card['request_id'])

    def test_agent_inbox_rejects_corrupt_projection_and_composed_request(self):
        for h in self.fixtures('inbox'):
            h.ready();p=h.response();h.deliver(h.prepare_response(p))
            original=[dict(r) for r in h.store.db.execute('SELECT * FROM transitions ORDER BY seq')]
            mutations=[]
            bad=copy.deepcopy(h.result);bad['reply_to']='0'*64;mutations.append((original[1]['seq'],bad))
            bad=copy.deepcopy(h.request);bad['payload']['prompt' if h.task.capability==BOUNDED_TEXT else 'query']='Different question';mutations.append((original[0]['seq'],bad))
            mutations.append((original[1]['seq'],h.request))
            for seq,bad in mutations:
                h.store.db.execute('UPDATE transitions SET body=? WHERE seq=?',(canonical(bad),seq))
                for owner in h.task.participants:
                    with self.subTest(scope=h.task.id,mutation=seq,owner=owner),self.assertRaises(Denied):h.boundaries[owner].dispatch({'method':'inbox'})
                for row in original:h.store.db.execute('UPDATE transitions SET body=? WHERE seq=?',(row['body'],row['seq']))
            # A valid-shaped but different request alone must also be rejected.
            h.store.db.execute('DELETE FROM transitions WHERE seq=?',(original[1]['seq'],))
            bad=copy.deepcopy(h.request);bad['payload']['prompt' if h.task.capability==BOUNDED_TEXT else 'query']='Different question'
            h.store.db.execute('UPDATE transitions SET body=?',(canonical(bad),))
            with self.assertRaises(Denied):h.boundaries[h.task.responder].dispatch({'method':'inbox'})

    def test_processing_transaction_failure_is_recoverable_without_redispatch(self):
        import sqlite3
        for h in self.fixtures('rollback'):
            h.auth.pair_all(h.gateway,h.now[0])
            card=h.flow.prepare(h.task.requester,'send',envelope=h.request);h.submit(card)
            h.box.dispatch(card['request_id'],h.receivers[h.task.responder])
            before=h.snapshot()
            h.store.db.execute("CREATE TRIGGER inject_failure BEFORE INSERT ON transitions BEGIN SELECT RAISE(ABORT, 'injected transition failure'); END")
            with self.assertRaises(sqlite3.IntegrityError):h.box.process_received(card['request_id'])
            h.store.db.execute('DROP TRIGGER inject_failure')
            self.assertEqual(before,h.snapshot());self.assert_views(h,[])
            h.reopen();self.assertEqual(h.box.status(card['request_id'])['attempts'],1)
            h.box.process_received(card['request_id']);self.assert_views(h,[h.request])
            self.assertEqual(h.box.status(card['request_id'])['attempts'],1)

    def test_real_process_corrupted_context_blocks_both_disclosure_surfaces(self):
        import sqlite3
        from tests.test_bounded_text_exchange import TextProcessTests
        h=TextProcessTests();h.setUp();self.addCleanup(h.doCleanups);h.ready()
        found=False
        for path in Path(h.service.directory.name).glob('*.sqlite3'):
            with sqlite3.connect(path) as db:
                if not db.execute("SELECT 1 FROM sqlite_master WHERE name='sessions'").fetchone():continue
                found=True
                original=db.execute('SELECT context FROM sessions').fetchone()[0]
                db.execute('UPDATE sessions SET context=?',('0'*64,));db.commit()
                for operation in (lambda:h.w.response_context(h.p['selector'],h.p['context'],h.responder),lambda:h.service._command('fixture_agent_call',actor=h.responder,command={'method':'inbox'})):
                    with self.assertRaises(Denied):operation()
                db.execute('UPDATE sessions SET context=?',(original,));db.commit()
                self.assertEqual(h.response_preview()['owner'],h.responder)
                break
        self.assertTrue(found)

    def test_alias_insertion_requires_coherent_history_not_active_authority(self):
        for h in self.fixtures('alias'):
            h.ready();p=h.response();card=h.prepare_response(p)
            b=h.boundaries[h.task.responder]
            command={'method':'propose','proposal_id':'first','envelope':p['envelope']}
            b.dispatch(command);b.prepare_owner_review('first')
            h.store.db.execute('UPDATE sessions SET context=?',('0'*64,));before=h.snapshot()
            with self.assertRaises(Denied):b.dispatch({**command,'proposal_id':'new-alias'})
            self.assertEqual(before,h.snapshot())
            h.store.db.execute('UPDATE sessions SET context=?',(h.session.context,))
            h.deliver(card)
            # A new alias for identical completed history is metadata, not resend.
            before=h.store.db.execute('SELECT COUNT(*) FROM transitions').fetchone()[0]
            b.dispatch({**command,'proposal_id':'new-alias'})
            self.assertEqual(b.prepare_owner_review('new-alias')['request_id'],card['request_id'])
            self.assertEqual(h.store.db.execute('SELECT COUNT(*) FROM transitions').fetchone()[0],before)
