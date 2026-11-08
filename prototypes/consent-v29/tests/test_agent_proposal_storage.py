"""Deterministic clock, capacity, detached JSON and transaction tests."""
import copy
import tempfile
import unittest
from pathlib import Path
from agent_proposals import AgentProposalBoundary
from generic_demo import fixture
from generic_session import GenericPersistentSession
from generic_owner_workflow import GenericOwnerWorkflow
from durable import LocalDelivery
from integrated_fixture import FixtureAuthorities
from owner_auth import SignedOwnerGateway
from encrypted_delivery import DurableEncryptedOutbox
from network import Denied


class AgentProposalStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.now=[1000];self.task,self.actors,self.message,_=fixture()
        self.store=LocalDelivery(Path(self.tmp.name)/'sender.sqlite3',clock=lambda:self.now[0]);self.addCleanup(self.store.close)
        self.session=GenericPersistentSession(self.store,self.actors,self.task)
        self.auth=FixtureAuthorities(self.task,1000)
        self.gateway=SignedOwnerGateway(self.session,self.auth.owner_roots)
        self.box=DurableEncryptedOutbox(self.gateway,self.auth.registry,self.auth.transport_keys)
        self.workflow=GenericOwnerWorkflow(self.gateway,self.box)
        self.boundary=AgentProposalBoundary(self.workflow,'alice')
    def propose(self, proposal_id='one', envelope=None):
        return self.boundary.dispatch({'method':'propose','proposal_id':proposal_id,'envelope':self.message if envelope is None else envelope})
    def count(self, table):return self.store.db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
    def pair(self):self.auth.pair_all(self.gateway,self.now[0])

    def test_expired_review_is_not_renewed_by_replays_or_aliases(self):
        self.pair();self.propose();card=self.boundary.prepare_owner_review('one')
        self.now[0]+=301
        for proposal_id in ('one','two'):
            self.assertEqual(self.propose(proposal_id)['state'],'expired')
            old=self.boundary.prepare_owner_review(proposal_id)
            self.assertEqual(old['request_id'],card['request_id'])
        self.assertEqual(self.count('owner_requests'),1)
        fresh=self.workflow.replace_review('alice',card['request_id'],old['review_digest'])
        self.assertEqual(fresh['state'],'pending')
        self.assertEqual(self.propose()['state'],'superseded')
        self.assertEqual(self.boundary.prepare_owner_review('one')['request_id'],card['request_id'])

    def test_stale_pair_versions_preserve_review_without_granting(self):
        self.pair();self.propose();card=self.boundary.prepare_owner_review('one')
        self.gateway.apply(self.auth.control('alice','revoke',{'peer':'bob','contact_version':1},self.now[0]))
        self.assertEqual(self.propose('two')['state'],'stale')
        self.assertEqual(self.boundary.prepare_owner_review('two')['request_id'],card['request_id'])
        self.assertEqual(self.count('owner_requests'),1)
        self.assertEqual(self.count('encrypted_outbox'),0)

    def test_failed_import_is_atomic_and_later_pairing_needs_explicit_import(self):
        self.propose()
        with self.assertRaises(Denied):self.boundary.prepare_owner_review('one')
        self.assertEqual(self.count('owner_requests'),0)
        self.pair()
        self.assertEqual(self.propose()['state'],'awaiting_owner_review')
        self.assertEqual(self.count('owner_requests'),0)
        self.assertEqual(self.boundary.prepare_owner_review('one')['state'],'pending')

    def test_limit_includes_aliases_and_exact_retry_survives_full_store(self):
        self.store.max_records=2
        self.propose();self.propose('two')
        with self.assertRaises(Denied):self.propose('three')
        bad=copy.deepcopy(self.message);bad['payload']['query']='different'
        with self.assertRaises(Denied):self.propose('four',bad)
        self.assertEqual(self.count('agent_proposals'),1)
        self.assertEqual(self.count('agent_proposal_ids'),2)
        self.assertEqual(self.propose()['state'],'awaiting_owner_review')

    def test_detached_input_and_output_and_malformed_types(self):
        original=copy.deepcopy(self.message)
        response=self.propose();response['state']='authorized'
        self.message['payload']['query']='mutated after call'
        self.pair();card=self.boundary.prepare_owner_review('one')
        self.assertEqual(card['envelope'],original)
        self.assertEqual(self.boundary.dispatch({'method':'proposal_status','proposal_id':'one'})['state'],'pending')
        for command in (None,[],{'method':[]},{'method':'inbox','owner':'bob'}, {'method':'propose','proposal_id':'one','envelope':object()}, {'method':'x','padding':'x'*13000}):
            with self.assertRaises(Denied):self.boundary.dispatch(command)

    def test_cancelled_staged_proposal_is_unavailable_and_cannot_import(self):
        self.propose()
        self.gateway.apply(self.auth.control('alice','cancel',{'meeting':self.task.id},1000))
        self.assertEqual(self.propose()['state'],'unavailable')
        with self.assertRaises(Denied):self.boundary.prepare_owner_review('one')
        self.assertEqual(self.count('owner_requests'),0)

    def test_other_task_proposal_ids_and_transitions_are_not_visible(self):
        from dataclasses import replace
        from generic_protocol import task_envelope
        from network import canonical
        other=replace(self.task,id='other-task')
        session=GenericPersistentSession(self.store,self.actors,other)
        authorities=FixtureAuthorities(other,1000)
        gateway=SignedOwnerGateway(session,authorities.owner_roots)
        workflow=GenericOwnerWorkflow(gateway,DurableEncryptedOutbox(gateway,authorities.registry,authorities.transport_keys))
        other_boundary=AgentProposalBoundary(workflow,'alice')
        message=task_envelope(other,'request',{'query':'Unrelated task secret','max_items':1})
        other_boundary.dispatch({'method':'propose','proposal_id':'unrelated','envelope':message})
        with self.assertRaises(Denied):self.boundary.dispatch({'method':'proposal_status','proposal_id':'unrelated'})
        self.propose('unrelated')  # Same actor and ID in different immutable scopes.
        self.assertNotEqual(other_boundary.dispatch({'method':'proposal_status','proposal_id':'unrelated'})['envelope_digest'],self.propose('unrelated')['envelope_digest'])
        # Trusted setup of an unrelated committed transition; no foreign task
        # data may escape the task-bound inbox query.
        self.store.db.execute('INSERT INTO transitions(session_id,delivery_id,body) VALUES (?,?,?)',
                              (other.id,'unrelated-delivery',canonical(message)))
        self.assertEqual(AgentProposalBoundary(self.workflow,'bob').dispatch({'method':'inbox'})['messages'],[])
        self.assertEqual(AgentProposalBoundary(workflow,'bob').dispatch({'method':'inbox'})['messages'][0]['envelope'],message)

    def test_actor_construction_excludes_third_party_and_wrong_workflow(self):
        for actor in ('charlie',None,[],True):
            with self.assertRaises(Denied):AgentProposalBoundary(self.workflow,actor)


if __name__=='__main__':unittest.main()
