"""Independent startup check: an unknown existing store cannot be reinitialised."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

from pilot.auth import LocalOwnerAuth
from pilot.crypto import fingerprint
from pilot.storage import StorageDenied
from conversation import ConversationLedger, ConversationDenied


class LedgerSchemaPrefixReview(unittest.TestCase):
    def test_unknown_table_cannot_acquire_new_ledger_sentinels(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            auth = LocalOwnerAuth(root / 'auth')
            ledger = None
            try:
                auth.bootstrap('fictional_owner', 'fictional_assistant', 'Fictional review password')
                principal = fingerprint(auth.public_identity())
                directory = root / 'ledger'
                directory.mkdir(mode=0o700)
                path = directory / 'conversation.sqlite'
                with sqlite3.connect(path) as db:
                    db.execute('CREATE TABLE sqliteXhidden (private_note TEXT)')
                path.chmod(0o600)
                with self.assertRaises((StorageDenied, ConversationDenied)):
                    ledger = ConversationLedger(directory, auth, {principal: auth})
                with sqlite3.connect(path) as db:
                    names = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                self.assertEqual(names, {'sqliteXhidden'})
            finally:
                if ledger is not None:
                    ledger.close()
                auth.close()
