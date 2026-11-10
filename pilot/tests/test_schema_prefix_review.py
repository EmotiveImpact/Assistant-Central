"""Independent fail-closed check for unknown tables near SQLite's reserved prefix."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

from pilot.auth import LocalOwnerAuth
from pilot.storage import RecordStorage, StorageDenied


class StorageSchemaPrefixReview(unittest.TestCase):
    def test_unknown_table_is_not_a_pristine_application_store(self):
        with tempfile.TemporaryDirectory() as directory:
            auth = LocalOwnerAuth(Path(directory) / 'auth')
            db = sqlite3.connect(':memory:')
            try:
                auth.bootstrap('fictional_owner', 'fictional_assistant', 'Fictional review password')
                db.execute('CREATE TABLE sqliteXhidden (private_note TEXT)')
                with self.assertRaises(StorageDenied):
                    RecordStorage(db, auth, create=True)
                self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='application_storage'").fetchone())
            finally:
                db.close()
                auth.close()
