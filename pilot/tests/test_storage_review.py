"""Independent encrypted-storage failure and cryptographic context regressions."""
import sqlite3
import unittest
from unittest.mock import patch

from pilot.auth import AuthError
from pilot.provider import ResponsesAdapter
from pilot.runtime import PilotRuntime
from pilot.storage import StoreLease, StorageDenied
from pilot.tests import test_storage as fixtures


class IndependentStorageReview(unittest.TestCase):
    setUp = fixtures.StorageTests.setUp
    close = fixtures.StorageTests.close
    item = fixtures.StorageTests.item
    workflow = fixtures.StorageTests.workflow
    legacy = fixtures.StorageTests.legacy
    restart = fixtures.StorageTests.restart

    def test_malformed_runtime_releases_lease_after_constructor_failure(self):
        self.a.close()
        (self.a.directory / 'runtime.sqlite').write_bytes(b'fictional corrupt sqlite bytes')
        with self.assertRaises(sqlite3.DatabaseError):
            PilotRuntime(self.a.directory, self.a.auth)
        lease = StoreLease(self.a.directory, exclusive=True)
        lease.close()

    def test_real_owner_cannot_choose_plaintext_provider_fixture(self):
        connection = sqlite3.connect(':memory:', isolation_level=None)
        self.addCleanup(connection.close)
        for opt_in in (False, True):
            with self.assertRaises(StorageDenied):
                ResponsesAdapter(connection, self.a.authorise_provider, self.a.auth.authenticate,
                                 legacy_storage_fixture=opt_in)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0], 0)

    def test_expired_owner_cannot_open_but_can_retain_late_ciphertext(self):
        encrypted = self.a.storage.seal('runtime_items', 'test', 'body', self.secret)
        self.a.auth.clock = lambda: 10000
        with self.assertRaises(AuthError):
            self.a.storage.open('runtime_items', 'test', 'body', encrypted)
        late = self.a.storage.seal('runtime_items', 'test', 'body', self.secret)
        self.assertNotIn(self.secret, late)
        with self.assertRaises(AuthError):
            self.a.storage.open('runtime_items', 'test', 'body', late)
