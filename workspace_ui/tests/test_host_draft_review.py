"""Independent uncertainty regression for the real committed helper boundary."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from workspace_ui.tests import test_host_drafts as fixtures


class IndependentHostReview(unittest.TestCase):
    def test_committed_dismissal_followed_by_helper_error_is_uncertain(self):
        fixture = fixtures.HostDraftHTTPTests(methodName='runTest')
        self.addCleanup(fixture.doCleanups)
        fixture.setUp()
        token = fixture.login()
        review = fixture.review(token)
        base = Path(__file__).resolve().parents[2]
        store_url = (base / 'agent_bridge/src/store.ts').as_uri()
        helper_url = (base / 'agent_bridge/src/owner_review.ts').as_uri()
        with tempfile.TemporaryDirectory() as temporary:
            wrapper = Path(temporary) / 'after-commit.mjs'
            wrapper.write_text(
                'import {DraftStore} from ' + json.dumps(store_url) + ';\n'
                'const original = DraftStore.prototype.dismissForOwner;\n'
                'DraftStore.prototype.dismissForOwner = function (...args) {\n'
                '  original.apply(this, args);\n'
                '  throw new Error("Injected post-commit helper fault");\n'
                '};\n'
                'await import(' + json.dumps(helper_url) + ');\n'
            )
            with patch('workspace_ui.host_draft_service.HELPER', wrapper):
                status, raw = fixture.request(
                    'POST', fixture.route + '/dismiss',
                    {'digest': review['digest'], 'reviewToken': review['reviewToken']}, token)
            self.assertEqual(fixture.review(token)['status']['state'], 'dismissed')
            with sqlite3.connect(fixture.launch['storePath']) as database:
                self.assertEqual(database.execute('SELECT count(*) FROM owner_dismissals').fetchone()[0], 1)
            self.assertNotIn(b'Injected post-commit', raw)
            self.assertNotIn(fixture.launch['keyHex'].encode(), raw)
            self.assertEqual(status, 503, 'A committed effect cannot be reported as a definite refusal')


if __name__ == '__main__':
    unittest.main()
