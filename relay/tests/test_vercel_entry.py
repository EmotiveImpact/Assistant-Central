# SPDX-License-Identifier: AGPL-3.0-only
import importlib.util
import os
import unittest

spec = importlib.util.spec_from_file_location('vercel_entry', os.path.join(os.path.dirname(__file__), '..', 'api', 'index.py'))
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


class OriginalTargetTests(unittest.TestCase):
    def test_rebuilds_the_signed_address(self):
        self.assertEqual(entry.original_target('/api/index?relay_path=v1/health'), '/v1/health')
        self.assertEqual(entry.original_target('/api/index?after=0&limit=5&relay_path=v1/mailboxes/ab/packets'),
                         '/v1/mailboxes/ab/packets?after=0&limit=5')
        self.assertEqual(entry.original_target('/api/index?relay_path=v1/mailboxes/ab/packets&through=7'),
                         '/v1/mailboxes/ab/packets?through=7')
        self.assertEqual(entry.original_target('/api/index?relay_path='), '/')
        self.assertEqual(entry.original_target('/v1/health'), '/v1/health')

    def test_refuses_ambiguous_or_smuggled_paths(self):
        self.assertIsNone(entry.original_target('/api/index?relay_path=a&relay_path=b'))
        self.assertIsNone(entry.original_target('/api/index?after=1'))
        self.assertIsNone(entry.original_target('/api/index?relay_path=v1%3Fx%3D1'))


if __name__ == '__main__':
    unittest.main()
