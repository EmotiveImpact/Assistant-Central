"""Controlled-child integration: bounded IPC releases the local workspace fence.

This is local lock/process evidence, not a remote stop or preemption guarantee.
"""
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ipc_test_support import child
from network import Denied
from owner_workspace import OwnerWorkspace


class WorkspaceDeadlineIntegration(unittest.TestCase):
    def test_partial_child_response_releases_lock_before_group_stop_commits(self):
        entered, release, stop_requested, stopped = (threading.Event() for _ in range(4))
        errors, results = [], []
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'one-command'
            process = child('import sys,pathlib,time; sys.stdin.buffer.readline(); '
                            'pathlib.Path(' + repr(str(marker)) + ').write_text("one"); '
                            'sys.stdout.buffer.write(b"{"); sys.stdout.buffer.flush(); time.sleep(60)')
            self.addCleanup(process.close)
            class ControlledService:
                def state(self, owner):
                    entered.set()
                    if not release.wait(3): raise RuntimeError('Test release missing')
                    return process.request({'owner':owner})
                def close(self): process.close()
            workspace = OwnerWorkspace()
            self.addCleanup(workspace.close)
            task = workspace.list_tasks()[0]
            with patch('owner_workspace.OwnerUIService',return_value=ControlledService()):
                workspace.create(task['selector'],task['context'])
            review = workspace.relationship_preview({'operation':'create','spec':{
                'group_id':'group-stalled','label':'Fictional stalled task',
                'members':[{'selector':task['selector'],'context':task['context']}]}})
            workspace.relationship_commit('create',review,'CREATE GROUP')
            stop_review = workspace.relationship_preview({'operation':'stop','group_id':'group-stalled'})
            def state_call():
                try: workspace.state(task['selector'],task['context'],'alice')
                except Exception as exc: errors.append(exc)
            def stop_call():
                stop_requested.set()
                try: results.append(workspace.relationship_commit('stop',stop_review,'STOP GROUP'))
                except Exception as exc: errors.append(exc)
                finally: stopped.set()
            action = threading.Thread(target=state_call)
            stopper = threading.Thread(target=stop_call)
            with patch('fixture_ipc._RESPONSE_TIMEOUT', .2):
                action.start()
                self.assertTrue(entered.wait(3))
                stopper.start()
                self.assertTrue(stop_requested.wait(3))
                self.assertFalse(stopped.is_set())  # Entered operation still owns the lock.
                release.set()
                action.join(3); stopper.join(3)
            self.assertFalse(action.is_alive()); self.assertFalse(stopper.is_alive())
            self.assertEqual(len(errors),1)
            self.assertIsInstance(errors[0],RuntimeError)
            self.assertIn('outcome may be unknown',str(errors[0]))
            self.assertEqual(marker.read_text(),'one')  # Lost reply did not mean no command.
            self.assertIsNotNone(process.process.poll())
            self.assertEqual(len(results),1); self.assertTrue(results[0]['stopped'])
            with self.assertRaises(Denied):
                workspace.action(task['selector'],task['context'],{'action':'next'})
            rows = workspace.list_tasks()
            self.assertTrue(rows[0]['local_work_stopped'])
            self.assertFalse(rows[1]['local_work_stopped'])
            workspace.close_task(task['selector'],task['context'])
            self.assertTrue(workspace.list_tasks()[0]['local_work_stopped'])

    def test_startup_timeout_cleans_owned_child_but_preserves_uncertain_slot(self):
        workspace = OwnerWorkspace()
        children, directories = [], []
        original_directory = tempfile.TemporaryDirectory
        def directory(*args, **kwargs):
            result = original_directory(*args, **kwargs)
            directories.append(result.name)
            return result
        def signer(*args, **kwargs):
            result = child('import os,time; os.write(1,b"{"); time.sleep(60)')
            children.append(result)
            self.addCleanup(result.close)
            return result
        garden, astronomy = workspace.list_tasks()
        with patch('owner_ui_service.JsonProcess',side_effect=signer), \
             patch('owner_ui_service.tempfile.TemporaryDirectory',side_effect=directory), \
             patch('fixture_ipc._RESPONSE_TIMEOUT', .2):
            with self.assertRaisesRegex(RuntimeError,'outcome may be unknown'):
                workspace.create(garden['selector'],garden['context'])
        self.assertEqual(len(children),1)
        self.assertIsNotNone(children[0].process.poll())
        self.assertTrue(all(not Path(name).exists() for name in directories))
        self.assertEqual(workspace.list_tasks()[0]['phase'],'startup_failed_cleanup_uncertain')
        with self.assertRaises(Denied): workspace.create(garden['selector'],garden['context'])
        # Unrelated actual fixture children still start; cleanup attempts all slots.
        workspace.create(astronomy['selector'],astronomy['context'])
        service = workspace._slots[astronomy['selector']]['service']
        try:
            with self.assertRaisesRegex(RuntimeError,'cleanup uncertain'): workspace.close()
        finally:
            service.close()
        self.assertTrue(service.closed)
        self.assertIsNotNone(service.executor.process.poll())
        self.assertTrue(all(s.process.poll() is not None for s in service.signers.values()))


if __name__ == '__main__': unittest.main()
