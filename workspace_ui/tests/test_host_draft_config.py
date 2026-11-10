"""Default-disabled launcher and strict private host configuration boundaries."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pilot.auth import LocalOwnerAuth
from pilot.server import RequestDenied
from workspace_ui.host_draft_service import HostDraftConfig, VERSION, load_host_draft_config
from workspace_ui.server import main


class HostDraftConfigTests(unittest.TestCase):
    def test_launcher_only_loads_host_config_when_explicitly_selected(self):
        with tempfile.TemporaryDirectory() as temp:
            owner = Path(temp) / 'owner'
            auth = LocalOwnerAuth(owner)
            auth.bootstrap('fictional_owner', 'fictional_agent', 'Fictional configuration password')
            auth.close()
            with patch('workspace_ui.server.WorkspaceHTTPServer') as factory, patch('workspace_ui.server.load_host_draft_config') as load:
                factory.return_value.origin = 'http://127.0.0.1:8877'
                main(['serve', '--directory', str(owner), '--port', '0'])
                load.assert_not_called()
                self.assertIsNone(factory.call_args.kwargs['host_draft_config'])
                main(['serve', '--directory', str(owner), '--port', '0', '--host-draft-config', '/private/host-drafts.json'])
                load.assert_called_once_with('/private/host-drafts.json')
                self.assertIs(factory.call_args.kwargs['host_draft_config'], load.return_value)
            with patch('workspace_ui.server.WorkspaceHTTPServer') as factory, patch('workspace_ui.server.load_host_draft_config', side_effect=RequestDenied('unavailable')):
                with self.assertRaises(RequestDenied):
                    main(['serve', '--directory', str(owner), '--port', '0', '--host-draft-config', '/private/missing.json'])
                factory.assert_not_called()

    def test_config_refuses_empty_duplicate_unknown_and_nonprivate_inputs(self):
        for value in ({'version': VERSION, 'connections': []}, {'version': 'unknown', 'connections': []},
                      {'version': VERSION, 'connections': [], 'command': 'untrusted'}):
            with self.assertRaises(RequestDenied): HostDraftConfig(value)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'launch.json'
            path.write_text('{}')
            path.chmod(0o600)
            item = {'id': 'host', 'owner_fingerprint': 'a'*64, 'launch_file': str(path)}
            for items in ([item, item], [item, dict(item, id='other')], [dict(item, command='untrusted')],
                          [dict(item, owner_fingerprint='model_owner')], [dict(item, id='../escape')]):
                with self.assertRaises(RequestDenied): HostDraftConfig({'version': VERSION, 'connections': items})
            config = Path(temp) / 'config.json'
            config.write_text('{"version":"x","version":"y","connections":[]}')
            config.chmod(0o600)
            with self.assertRaises(RequestDenied): load_host_draft_config(config)


if __name__ == '__main__':
    unittest.main()
