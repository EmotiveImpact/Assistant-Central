"""Offline Anthropic Messages route tests. No API is called; the SDK client is faked."""
import json
import unittest

from pilot.provider import (AnthropicMessagesSDK, ANTHROPIC_ENDPOINT, ProviderDenied, ProviderOutcomeUnknown,
                            ResponsesAdapter)
from pilot.tests.test_provider import ProviderTests as _Base


def message(text='SYNTHETIC ONLY: Three paper moons.', stop='end_turn', blocks=None, tokens=12):
    return {'id': 'msg_fixture', 'type': 'message', 'role': 'assistant', 'model': 'claude-opus-5-5',
            'content': blocks if blocks is not None else [{'type': 'thinking', 'thinking': '', 'signature': 'sig'},
                                                          {'type': 'text', 'text': text}],
            'stop_reason': stop, 'usage': {'input_tokens': 40, 'output_tokens': tokens}}


class FakeResponse:
    def __init__(self, value):
        self.value = value

    def model_dump_json(self):
        return json.dumps(self.value)


class FakeClient:
    def __init__(self, reply, calls):
        self.reply, self.calls = reply, calls
        self.messages = self

    def create(self, **request):
        self.calls.append(request)
        if isinstance(self.reply, Exception):
            raise self.reply
        return FakeResponse(self.reply)


class AnthropicRouteTests(_Base):
    def setUp(self):
        super().setUp()
        self.binding['provider'] = 'anthropic'
        self.binding['model'] = 'claude-opus-5-5'
        self.sdk_calls, self.keys, self.reply = [], [], message()
        self.transport = self.live()
        self.adapter = self.make_adapter(allow_live=True)

    def live(self, enabled=True):
        def factory(key, timeout):
            self.keys.append(key)
            return FakeClient(self.reply, self.sdk_calls)
        return AnthropicMessagesSDK(lambda: 'sk-ant-fictional-key-0123456789', enabled=enabled, client_factory=factory)

    def run_once(self):
        result = self.adapter.prepare('owner-session', 'run-one', self.binding)
        self.adapter.approve('owner-session', 'run-one', result['review_digest'], expires=self.now + 600)
        return self.adapter.dispatch('owner-session', 'run-one')

    def test_review_shows_exact_messages_request_without_tools(self):
        self.adapter.prepare('owner-session', 'run-one', self.binding)
        review = self.adapter.review('owner-session', 'run-one')['review']
        self.assertEqual(review['endpoint'], ANTHROPIC_ENDPOINT)
        request = review['request']
        self.assertEqual(set(request), {'model', 'system', 'max_tokens', 'messages', 'output_config'})
        self.assertEqual(request['messages'], [{'role': 'user', 'content': self.text}])
        self.assertNotIn('tools', request)

    def test_one_approved_call_returns_text_and_never_repeats(self):
        status = self.run_once()
        self.assertEqual(status['state'], 'completed')
        self.assertEqual(len(self.sdk_calls), 1)
        self.assertEqual(self.sdk_calls[0]['model'], 'claude-opus-5-5')
        result = self.adapter.result('owner-session', 'run-one')
        self.assertEqual(result['text'], 'SYNTHETIC ONLY: Three paper moons.')
        with self.assertRaises(ProviderDenied):
            self.adapter.dispatch('owner-session', 'run-one')
        self.assertEqual(len(self.sdk_calls), 1)

    def test_refusal_truncation_and_tool_use_are_not_results(self):
        for reply in (message(stop='refusal'), message(stop='max_tokens'),
                      message(blocks=[{'type': 'tool_use', 'id': 't', 'name': 'x', 'input': {}}]),
                      message(tokens=10_000)):
            with self.subTest(reply=reply['stop_reason']):
                self.setUp()
                self.reply = reply
                with self.assertRaises(ProviderOutcomeUnknown):
                    self.run_once()
                self.assertEqual(self.adapter.status('owner-session', 'run-one')['state'], 'uncertain')

    def test_sdk_error_is_uncertain_and_hides_the_key(self):
        self.reply = RuntimeError('sk-ant-fictional-key-0123456789 leaked?')
        with self.assertRaises(ProviderOutcomeUnknown) as caught:
            self.run_once()
        self.assertNotIn('sk-ant', str(caught.exception))
        self.assertEqual(self.adapter.status('owner-session', 'run-one')['error_code'], 'transport_error')

    def test_disabled_transport_or_live_policy_refuses_before_any_call(self):
        self.transport = self.live(enabled=False)
        self.adapter = self.make_adapter(allow_live=True)
        with self.assertRaises((ProviderDenied, ProviderOutcomeUnknown)):
            self.run_once()
        self.assertEqual(self.sdk_calls, [])

    def test_unapproved_run_never_reaches_the_sdk(self):
        self.adapter.prepare('owner-session', 'run-one', self.binding)
        with self.assertRaises(ProviderDenied):
            self.adapter.dispatch('owner-session', 'run-one')
        self.assertEqual(self.sdk_calls, [])

    def test_real_client_uses_no_retries(self):
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.skipTest('optional anthropic package not installed')
        client = AnthropicMessagesSDK(lambda: 'k' * 20, enabled=True)._client('k' * 20)
        self.assertEqual(client.max_retries, 0)


# Only run the Anthropic-specific tests here; the OpenAI suite runs from its own module.
for _name in [n for n in vars(_Base) if n.startswith('test_')]:
    setattr(AnthropicRouteTests, _name, None)
del _Base

if __name__ == '__main__':
    unittest.main()
