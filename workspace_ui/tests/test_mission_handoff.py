"""A shared local agreement, two distinct worker processes and a reviewed return."""
from contextlib import contextmanager
from pathlib import Path
import tempfile
import threading
import time
import unittest

from pilot.auth import LocalOwnerAuth
from pilot.crypto import digest, fingerprint
from pilot.demo import request, running_process
from pilot.runtime import PilotRuntime
from workspace_ui.conversation_fixture import PASSWORD, seed_conversations
from workspace_ui.server import WorkspaceHTTPServer


@contextmanager
def workspace(root, config):
    server = WorkspaceHTTPServer(root / 'alice', conversation_config=config)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.origin
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def owner(url, name=None):
    login = request(url, 'POST', '/api/session', {'password': PASSWORD, **({'account': name} if name else {})})
    def call(path, body=None):
        return request(url, 'POST' if body is not None else 'GET', path, body, login['token'])
    return call


def missions(call):
    room = '/api/conversations/thread_1'
    binding = call(room)['binding']
    bound = {k: binding[k] for k in ('member_epoch', 'policy_generation')}
    return lambda action, **fields: call(room + '/missions/' + action, {'binding': bound, **fields})


def decide(call, item, choice):
    path = '/api/items/' + item
    review = call(path + '/review')
    payload = {'review_digest': review['review_digest']}
    if choice == 'release':
        return call(path + '/release', payload)
    return call(path + '/decision', {**payload, 'decision': choice})


class MissionHandoffTests(unittest.TestCase):
    def test_two_process_exact_return_and_independent_owner_decisions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = seed_conversations(root)
            identities = {}
            for name in ('alice','bob'):
                auth = LocalOwnerAuth(root / name)
                identities[name] = auth.public_identity()
                auth.close()
            # Independently supplied fixture pins. Endpoint configuration follows
            # at runtime, when the real ephemeral ports are known.
            auth = LocalOwnerAuth(root / 'alice')
            runtime = PilotRuntime(root / 'alice', auth)
            try:
                runtime.enrol_peer(auth.login(PASSWORD), identities['bob'], fingerprint(identities['bob']))
            finally:
                runtime.close()
                auth.close()
            goal = 'Private editorial direction'
            agreed = {'goal': goal, 'deliverable': 'A returned fictional note',
                      'executor': fingerprint(identities['bob']), 'cap_microusd': 300,
                      'criteria': [{'kind':'contains','value':'Fictional research plan'},
                                   {'kind':'max_utf8_bytes','value':1},
                                   {'kind':'human_review','value':'Check the editorial tone'}]}
            brief = 'Draft a fictional community garden note.'
            with workspace(root,config) as url:
                alice, bob = owner(url,'alice'), owner(url,'bob')
                a, b = missions(alice), missions(bob)
                view = a('create',request_id='original',terms=agreed,expires_at=time.time()+1200)
                pid = view['proposal']['statement']['id']
                commitment = digest(view['proposal']['statement'])
                for call in (a,b):
                    review = call('review',proposal_id=pid)
                    if call is a:
                        with self.assertRaises(AssertionError):
                            b('approve',proposal_id=pid,review_digest=review['review_digest'])
                    call('approve',proposal_id=pid,review_digest=review['review_digest'])
                with self.assertRaises(AssertionError):
                    b('draft',proposal_id=pid,proposal_digest=commitment,brief=brief,task_id='job')
                draft = a('draft',proposal_id=pid,proposal_digest=commitment,brief=brief,task_id='job')
                task = draft['id']
                self.assertEqual(draft['state'],'draft')
                packet = alice('/api/items/'+task+'/review')
                self.assertNotIn(goal,packet['content'])
                self.assertNotIn('editorial tone',packet['content'])
                decide(alice,task,'release')

            with running_process(root/'alice') as (first,pid_a), running_process(root/'bob',synthetic_workflow=True) as (second,pid_b):
                self.assertNotEqual(pid_a,pid_b)
                alice,bob = owner(first),owner(second)
                for actor,peer,endpoint in ((alice,'bob',second),(bob,'alice',first)):
                    actor('/api/peers',{'public_identity':identities[peer],'expected_fingerprint':fingerprint(identities[peer]),'endpoint':endpoint})
                def exchange():
                    for _ in range(2):
                        alice('/api/exchange',{})
                        bob('/api/exchange',{})
                exchange()
                decide(bob,task,'accept')
                run = bob('/api/items/'+task+'/workflow',{})['run_id']
                path = '/api/workflows/'+run
                review = bob(path+'/review')
                self.assertEqual(review['review']['request']['input'],brief)
                self.assertEqual(review['review']['mission_quote']['cap_microusd'],300)
                with self.assertRaises(AssertionError):
                    bob(path+'/run',{'review_digest':review['review_digest']})
                bob(path+'/approve',{'review_digest':review['review_digest'],'expires':time.time()+600})
                result = bob(path+'/run',{'review_digest':review['review_digest']})
                self.assertEqual(result['mission_usage']['actual_microusd'],20)
                artifact = bob(path+'/stage',{'review_digest':bob(path+'/result')['review_digest']})['artifact_id']
                decide(bob,artifact,'release')
                exchange()
                self.assertIn('accept',alice('/api/items/'+artifact+'/review')['allowed_actions'])

            with workspace(root,config) as url:
                alice,bob = owner(url,'alice'),owner(url,'bob')
                a,b = missions(alice),missions(bob)
                report = a('evaluate',proposal_id=pid,artifact_id=artifact)
                self.assertEqual(report['parent_task_id'],task)
                self.assertEqual([f['status'] for f in report['findings']],['passed','failed','needs_owner_review'])
                self.assertTrue(report['recipient_decision_required'])
                self.assertFalse(report['all_checks_passed'])
                with self.assertRaises(AssertionError):
                    b('evaluate',proposal_id=pid,artifact_id=artifact)
                with self.assertRaises(AssertionError):
                    a('evaluate',proposal_id=pid,artifact_id=task)
                self.assertEqual(decide(alice,artifact,'reject')['state'],'rejected')
                new = a('create',request_id='revision',terms={**agreed,'goal':'Revised goal'},expires_at=time.time()+900,replaces=pid)
                self.assertFalse(new['all_owners_approved'])
                with self.assertRaises(AssertionError):
                    a('draft',proposal_id=pid,proposal_digest=commitment,brief=brief,task_id='stale')
