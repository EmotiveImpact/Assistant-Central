"""Independent composition review: offline boundary and concurrency regression tests."""
import concurrent.futures
import threading
import unittest
from unittest.mock import MagicMock, patch

from network import Denied, canonical
from owner_workspace import OwnerWorkspace
from task_composer import preview, parse_startup
from task_fixtures import SELECTORS, fixture
from generic_protocol import task_context_digest


def spec(n='review'):
    return dict(selector='custom-'+n,task_id='task-'+n,conversation_id='conversation-'+n,
                requester='alice',query='Fictional public examples',max_items=2)


class IndependentComposerReview(unittest.TestCase):
    def test_every_accepted_unicode_spec_round_trips_startup(self):
        for query in ['😀'*512, '𐀀'*512, 'é'*512, 'x'*512]:
            value=spec();value['query']=query
            with self.subTest(codepoint=ord(query[0])):
                preview(value)
                self.assertEqual(parse_startup(canonical(value)), value)

    def test_parallel_identical_creation_allocates_only_once(self):
        workspace=OwnerWorkspace();barrier=threading.Barrier(12)
        value=spec();review=preview(value)
        def create(_):
            barrier.wait()
            try:
                workspace.compose(value,review['review_digest'],'CREATE TASK')
                return True
            except Denied:
                return False
        with patch('owner_workspace.OwnerUIService',return_value=MagicMock()) as constructor:
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                outcomes=list(pool.map(create,range(12)))
            self.assertEqual(sum(outcomes),1)
            self.assertEqual(constructor.call_count,1)
            workspace.close()

    def test_parallel_unique_creation_cannot_exceed_capacity(self):
        workspace=OwnerWorkspace();barrier=threading.Barrier(12)
        def create(i):
            value=spec(str(i));review=preview(value);barrier.wait()
            try:
                workspace.compose(value,review['review_digest'],'CREATE TASK')
                return True
            except Denied:
                return False
        with patch('owner_workspace.OwnerUIService',return_value=MagicMock()) as constructor:
            with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
                outcomes=list(pool.map(create,range(12)))
            self.assertEqual(sum(outcomes),8)
            self.assertEqual(constructor.call_count,8)
            self.assertEqual(len(workspace.list_tasks()),10)
            workspace.close()

    def test_mutating_caller_spec_and_catalog_does_not_change_active_scope(self):
        workspace=OwnerWorkspace();value=spec();review=preview(value)
        with patch('owner_workspace.OwnerUIService',return_value=MagicMock()):
            row=workspace.compose(value,review['review_digest'],'CREATE TASK')
            value['query']='Replaced caller text';row['context']='wrong'
            rows=workspace.list_tasks();rows[-1]['selector']='wrong'
            actual=workspace.list_tasks()[-1]
            self.assertEqual(actual['context'],review['context'])
            self.assertEqual(actual['selector'],review['selector'])
            workspace.close()

    def test_existing_catalog_scope_hash_excludes_optional_commitment(self):
        # Independently reconstruct pre-composition canonical shape, proving that
        # adding a nullable Task field did not change the existing catalog hash.
        from network import digest
        for selector in SELECTORS:
            task=fixture(selector)[0]
            self.assertNotIn('composition_digest',task.to_dict())
            legacy={'id':task.id,'conversation':task.conversation.to_dict(),
                    'requester':task.requester,'responder':task.responder,
                    'capability':task.capability,'operation':task.operation}
            self.assertEqual(task_context_digest(task),
                             digest({'domain':'agent-network-task-context/v2','task':legacy}))

    def test_catalog_task_identity_cannot_be_shadowed(self):
        workspace=OwnerWorkspace()
        with patch('owner_workspace.OwnerUIService',side_effect=AssertionError('allocated')):
            for selector in SELECTORS:
                value=spec();value['task_id']=fixture(selector)[0].id
                with self.assertRaises(Denied):
                    workspace.compose(value,preview(value)['review_digest'],'CREATE TASK')
        self.assertEqual(len(workspace.list_tasks()),2)

if __name__=='__main__':unittest.main()
