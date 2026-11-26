"""NIP-44 checks adapted from pinned A4A sdk-python/tests/test_nip44.py.

Copyright (c) 2026 A4A Network, MIT; see vendor/a4a/LICENSE and UPSTREAM.json.
Vector license is separately retained in vendor/a4a_sdk/nip44_vectors.LICENSE.txt.
Modifications: unittest harness instead of pytest; fixture-only, no transport.
"""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest
from vendor.a4a_sdk import crypto, event, keys, nip44

ROOT = Path(__file__).resolve().parent.parent
VECTORS_FILE = ROOT / 'vendor/a4a_sdk/nip44_vectors.json'
VECTORS = json.loads(VECTORS_FILE.read_text())['v2']


class PinnedSourceTests(unittest.TestCase):
    def test_every_vendored_source_matches_pinned_blob_and_sha256(self):
        manifest = json.loads((ROOT / 'UPSTREAM.json').read_text())
        self.assertEqual(manifest['revision'], '6b111e3fb6fdf61f0e790ae84e2db86c5bb86b7e')
        for entry in manifest['files']:
            data = (ROOT / entry['local']).read_bytes()
            with self.subTest(file=entry['local']):
                self.assertEqual(hashlib.sha256(data).hexdigest(), entry['sha256'])
                self.assertEqual(hashlib.sha1(b'blob ' + str(len(data)).encode() + bytes([0]) + data).hexdigest(), entry['git_blob_sha1'])
                self.assertIn(manifest['revision'], entry['url'])

    def test_original_nine_sdk_event_checks_unchanged(self):
        package = types.ModuleType('a4a'); package.crypto = crypto
        aliases = {'a4a': package, 'a4a.crypto': crypto, 'a4a.event': event, 'a4a.keys': keys}
        previous = {name: sys.modules.get(name) for name in aliases}
        try:
            sys.modules.update(aliases)
            spec = importlib.util.spec_from_file_location('pinned_event_tests', ROOT / 'vendor/a4a_sdk/test_event_original.py')
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            checks = [fn for name, fn in vars(module).items() if name.startswith('test_') and callable(fn)]
            self.assertEqual(len(checks), 9)
            for check in checks:
                with self.subTest(check=check.__name__): check()
        finally:
            for name, value in previous.items():
                if value is None: sys.modules.pop(name, None)
                else: sys.modules[name] = value


class OfficialVectorTests(unittest.TestCase):
    def test_official_vector_file_checksum(self):
        self.assertEqual(hashlib.sha256(VECTORS_FILE.read_bytes()).hexdigest(),
                         '269ed0f69e4c192512cc779e78c555090cebc7c785b609e338a62afc3ce25040')

    def test_conversation_key_vectors(self):
        cases = VECTORS['valid']['get_conversation_key']
        self.assertGreaterEqual(len(cases), 30)
        for i, case in enumerate(cases):
            with self.subTest(case=i):
                self.assertEqual(nip44._conversation_key(case['sec1'], case['pub2']).hex(), case['conversation_key'])

    def test_message_key_vectors(self):
        cases = VECTORS['valid']['get_message_keys']
        self.assertGreaterEqual(len(cases['keys']), 30)
        for i, case in enumerate(cases['keys']):
            with self.subTest(case=i):
                actual = nip44._message_keys(bytes.fromhex(cases['conversation_key']), bytes.fromhex(case['nonce']))
                self.assertEqual(tuple(value.hex() for value in actual), (case['chacha_key'], case['chacha_nonce'], case['hmac_key']))

    def test_padding_vectors(self):
        for plain, padded in VECTORS['valid']['calc_padded_len']:
            with self.subTest(length=plain): self.assertEqual(nip44._calc_padded_len(plain), padded)

    def test_encrypt_decrypt_known_answer_vectors(self):
        cases = VECTORS['valid']['encrypt_decrypt']; self.assertGreaterEqual(len(cases), 5)
        for i, case in enumerate(cases):
            with self.subTest(case=i):
                pub1, pub2 = keys.Keys(case['sec1']).pubkey_hex, keys.Keys(case['sec2']).pubkey_hex
                ck = nip44._conversation_key(case['sec1'], pub2)
                self.assertEqual(ck.hex(), case['conversation_key'])
                self.assertEqual(nip44._conversation_key(case['sec2'], pub1), ck)
                self.assertEqual(nip44._encrypt_with_nonce(case['plaintext'], ck, bytes.fromhex(case['nonce'])), case['payload'])
                self.assertEqual(nip44.decrypt(case['payload'], case['sec2'], pub1), case['plaintext'])

    def test_long_message_known_answer_vectors(self):
        for i, case in enumerate(VECTORS['valid']['encrypt_decrypt_long_msg']):
            with self.subTest(case=i):
                plaintext = case['pattern'] * case['repeat']
                self.assertEqual(hashlib.sha256(plaintext.encode()).hexdigest(), case['plaintext_sha256'])
                payload = nip44._encrypt_with_nonce(plaintext, bytes.fromhex(case['conversation_key']), bytes.fromhex(case['nonce']))
                self.assertEqual(hashlib.sha256(payload.encode('ascii')).hexdigest(), case['payload_sha256'])

    def test_invalid_curve_keys_are_rejected(self):
        for i, case in enumerate(VECTORS['invalid']['get_conversation_key']):
            with self.subTest(case=i), self.assertRaises(nip44.Nip44Error):
                nip44._conversation_key(case['sec1'], case['pub2'])

    def test_invalid_payload_vectors_are_rejected_at_the_correct_key(self):
        for i, case in enumerate(VECTORS['invalid']['decrypt']):
            with self.subTest(case=i), self.assertRaises(nip44.Nip44Error):
                nip44._decrypt_with_key(case['payload'], bytes.fromhex(case['conversation_key']))

    def test_invalid_plaintext_lengths_are_rejected(self):
        for length in VECTORS['invalid']['encrypt_msg_lengths']:
            with self.subTest(length=length), self.assertRaises(nip44.Nip44Error):
                nip44._pad('a' * length)
