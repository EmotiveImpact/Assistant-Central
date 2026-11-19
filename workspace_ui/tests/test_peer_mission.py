"""Direct owner-to-owner task with separate SDK queues and no shared coordinator."""
from pathlib import Path
import secrets
import tempfile
import time
import unittest

from pilot.workflow_demo import TwoProcessWorkflow
from pilot.demo import request
from workspace_ui.host_draft_fixture import sdk_seed


class PeerMissionTests(unittest.TestCase):
    def test_separate_sdk_drafts_and_owner_mediated_return(self):
        with tempfile.TemporaryDirectory() as directory, TwoProcessWorkflow() as pilot:
            root = Path(directory)
            # These SDK drafts use independently configured sessions and stores.
            # Public fixture words are re-authored by the scripted owners below.
            # Nothing reads personal assistant history or releases an SDK draft.
            def local_sdk_note(side, operation, flag, reference):
                name = 'worker' if side else 'requester'
                home = root / name
                home.mkdir(mode=0o700)
                launch = {'storePath':str(home/'queue.sqlite'), 'keyHex':secrets.token_hex(32),
                          'binding':{'ownerId':pilot.receiver_pin if side else pilot.sender_pin,
                          'hostId':name,'sessionId':name+'_session','conversationId':'mission_room',
                          'recipientId':'fictional_peer','expiresAt':int(time.time()*1000)+600000}}
                note = {'title':'Private planning draft','requestId':reference,'instruction':'Private '+name+' checklist for '+reference}
                saved = sdk_seed(launch,home,note,operation)
                self.assertTrue(saved[flag] and saved['mcp'])
            def call(side, path, body=None):
                url, token = pilot.owner(side)
                return request(url,'POST' if body is not None else 'GET',path,body,token)
            terms = {'executor':pilot.receiver_pin,'goal':'Review a fictional brief','deliverable':'A note',
                     'cap_microusd':276,'criteria':[{'kind':'contains','value':'Fictional research plan'}]}
            offer = {'agreed':terms,'brief':'Independently authored fictional text.','expires':time.time()+900,
                     'task_id':'peer-one','permit_fixture':False}
            denied = call(False,'/api/mission-offers',offer)['id']
            pilot.item_action(denied,'release')
            pilot.settle()
            pilot.item_action(denied,'decision',True,'accept')
            with self.assertRaises(AssertionError):
                pilot.prepare(denied)
            local_sdk_note(False,'seed','officialRunner','peer-two')
            task = call(False,'/api/mission-offers',{**offer,'task_id':'peer-two','permit_fixture':True})['id']
            pilot.item_action(task,'release')
            pilot.settle()
            pilot.item_action(task,'decision',True,'accept')
            # The executing owner selects this public reference after accepting the
            # exact task. The SDK receives no peer brief, criteria or return content.
            accepted = next(item for item in pilot.state(True)['items'] if item['id'] == task)
            self.assertEqual(accepted['task_id'], 'peer-two')
            local_sdk_note(True,'cursor-seed','officialCursorHost',accepted['task_id'])
            run = pilot.prepare(task)['run_id']
            review = pilot.workflow(run,'review')['review']
            self.assertEqual(review['request']['input'],offer['brief'])
            approved = pilot.approve(run)
            result = pilot.workflow(run,'run',{'review_digest':approved})
            self.assertEqual(result['mission_usage']['held_microusd'],0)
            art = pilot.workflow(run,'stage',{'review_digest':pilot.workflow(run,'result')['review_digest']})['artifact_id']
            pilot.item_action(art,'release',True)
            pilot.settle()
            report = call(False,'/api/items/'+art+'/mission-evidence')
            self.assertTrue(report['all_checks_passed'])
            self.assertEqual(report['parent_task_id'],task)
            self.assertIn('accept',pilot.item_review(art)['allowed_actions'])
            self.assertEqual(pilot.item_action(art,'decision',decision='accept')['state'],'accepted')
