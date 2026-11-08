"""Independent decoded-stream boundary tests; no native host or network claim."""
import copy
from contextlib import asynccontextmanager
import io
import json
import logging
import unittest

import anyio
from mcp import ClientSession, types
from mcp.shared.message import SessionMessage
from mcp_proposal_adapter import ProposalMCPAdapter, SUPPORTED_VERSIONS
from network import digest
from task_fixtures import fixture


@asynccontextmanager
async def peer(adapter):
    tx, rx = anyio.create_memory_object_stream(16)
    out, responses = anyio.create_memory_object_stream(16)
    async with anyio.create_task_group() as group:
        group.start_soon(adapter.run, rx, out)
        try:
            yield tx, responses
        finally:
            await tx.aclose()
            group.cancel_scope.cancel()
    for stream in (tx, rx, out, responses):
        await stream.aclose()


def message(method, ident=None, params=None):
    value = {'jsonrpc': '2.0', 'method': method}
    if ident is not None:
        value['id'] = ident
    if params is not None:
        value['params'] = params
    return SessionMessage(types.JSONRPCMessage.model_validate(value))


async def exchange(tx, rx, method, ident, params=None):
    await tx.send(message(method, ident, params))
    with anyio.fail_after(3):
        return (await rx.receive()).message.model_dump(mode='json', exclude_none=True)


async def initialize(tx, rx, **extra):
    result = await exchange(tx, rx, 'initialize', 'init', {
        'protocolVersion': extra.pop('version', '2025-11-25'),
        'capabilities': extra.pop('capabilities', {}),
        'clientInfo': {'name': 'untrusted-peer', 'version': '1', 'title': 'Untrusted owner claim'},
        **extra})
    await tx.send(message('notifications/initialized'))
    return result


class IndependentMCPAdapterReview(unittest.TestCase):
    def setUp(self):
        self.task, _, self.envelope, self.result = fixture()
        self.calls = []

    def dispatch(self, command):
        self.calls.append(copy.deepcopy(command))
        if command['method'] == 'inbox':
            return {'messages': [], 'payload_trust': 'untrusted_inert'}
        return {'proposal_id': command['proposal_id'], 'envelope_digest': digest(self.envelope),
                'state': 'awaiting_owner_review', 'delivery_state': None}

    def run_async(self, fn):
        anyio.run(fn)

    def test_real_sdk_client_only_three_tools_and_inert_capabilities(self):
        async def run():
            adapter = ProposalMCPAdapter(self.task, 'alice', self.dispatch)
            async with peer(adapter) as (tx, rx):
                async with ClientSession(rx, tx) as client:
                    initialized = await client.initialize()
                    caps = initialized.capabilities.model_dump(exclude_none=True)
                    self.assertEqual(set(caps), {'tools'})
                    listing = await client.list_tools()
                    self.assertEqual({t.name for t in listing.tools}, {'propose', 'proposal_status', 'inbox'})
                    result = await client.call_tool('inbox', {})
                    self.assertFalse(result.isError)
                    self.assertEqual(json.loads(result.content[0].text)['messages'], [])
            self.assertEqual(self.calls, [{'method': 'inbox'}])
        self.run_async(run)

    def test_metadata_cannot_choose_actor_or_owner_method(self):
        async def run():
            async with peer(ProposalMCPAdapter(self.task, 'alice', self.dispatch)) as (tx, rx):
                init = await initialize(tx, rx, capabilities={'roots': {'listChanged': True}, 'sampling': {}, 'elicitation': {}}, _meta={'actor': 'bob'})
                self.assertEqual(set(init['result']['capabilities']), {'tools'})
                denied = await exchange(tx, rx, 'tools/call', 1, {'name': 'owner_sign', 'arguments': {}, '_meta': {'actor': 'owner'}})
                self.assertTrue(denied['result']['isError'])
                ok = await exchange(tx, rx, 'tools/call', 2, {'name': 'inbox', 'arguments': {}, '_meta': {'actor': 'bob', 'route': 'secret'}})
                self.assertFalse(ok['result']['isError'])
                self.assertEqual(self.calls, [{'method': 'inbox'}])
        self.run_async(run)

    def test_supported_legacy_versions_and_future_fallback(self):
        async def run():
            for version in (*SUPPORTED_VERSIONS, '2026-07-28'):
                async with peer(ProposalMCPAdapter(self.task, 'alice', self.dispatch)) as (tx, rx):
                    result = await initialize(tx, rx, version=version)
                    negotiated = result['result']['protocolVersion']
                    self.assertEqual(negotiated, version if version in SUPPORTED_VERSIONS else '2025-11-25')
        self.run_async(run)

    def test_strict_application_types_and_cross_scope(self):
        async def run():
            async with peer(ProposalMCPAdapter(self.task, 'alice', self.dispatch)) as (tx, rx):
                await initialize(tx, rx)
                bad = []
                for value in (True, 1.0, '1', 0, 6):
                    env = copy.deepcopy(self.envelope)
                    env['payload']['max_items'] = value
                    bad.append(env)
                for field, value in (('sender', 'bob'), ('task', 'alien'), ('context', '0'*64)):
                    bad.append({**self.envelope, field: value})
                for n, env in enumerate(bad):
                    response = await exchange(tx, rx, 'tools/call', n, {'name': 'propose', 'arguments': {'proposal_id': 'test', 'envelope': env}})
                    self.assertTrue(response['result']['isError'])
                self.assertEqual(self.calls, [])
        self.run_async(run)

    def test_null_arguments_and_tool_notifications_never_dispatch(self):
        async def run():
            async with peer(ProposalMCPAdapter(self.task, 'alice', self.dispatch)) as (tx, rx):
                await initialize(tx, rx)
                response = await exchange(tx, rx, 'tools/call', 1, {'name': 'inbox', 'arguments': None})
                self.assertIn('error', response)
                await tx.send(message('tools/call', params={'name': 'inbox', 'arguments': {}}))
                await exchange(tx, rx, 'ping', 2)
                self.assertEqual(self.calls, [])
        self.run_async(run)

    def test_duplicate_request_consumed_after_uncertain_commit(self):
        def committed(command):
            self.calls.append(command)
            raise RuntimeError('SECRET_OWNER_KEY post-commit failure')
        async def run():
            async with peer(ProposalMCPAdapter(self.task, 'alice', committed)) as (tx, rx):
                await initialize(tx, rx)
                args = {'name': 'propose', 'arguments': {'proposal_id': 'test', 'envelope': self.envelope}}
                first = await exchange(tx, rx, 'tools/call', 'same', args)
                self.assertTrue(first['result']['isError'])
                self.assertNotIn('SECRET_OWNER_KEY', json.dumps(first))
                second = await exchange(tx, rx, 'tools/call', 'same', args)
                self.assertIn('error', second)
                self.assertEqual(len(self.calls), 1)
        self.run_async(run)

    def test_owner_output_fields_and_cross_context_inbox_are_redacted(self):
        outputs = [{'messages': [], 'payload_trust': 'untrusted_inert', 'owner_key': 'PRIVATE_KEY'},
                   {'messages': [{'envelope': self.envelope, 'envelope_digest': digest(self.envelope)}], 'payload_trust': 'untrusted_inert'}]
        async def run():
            for output in outputs:
                async with peer(ProposalMCPAdapter(self.task, 'alice', lambda command: output)) as (tx, rx):
                    await initialize(tx, rx)
                    result = await exchange(tx, rx, 'tools/call', 1, {'name': 'inbox', 'arguments': {}})
                    self.assertTrue(result['result']['isError'])
                    self.assertNotIn('PRIVATE_KEY', json.dumps(result))
                    self.assertNotIn('envelope', json.dumps(result))
        self.run_async(run)

    def test_malformed_protocol_metadata_does_not_echo_into_diagnostics(self):
        async def run():
            log = io.StringIO()
            handler = logging.StreamHandler(log)
            logging.getLogger().addHandler(handler)
            try:
                async with peer(ProposalMCPAdapter(self.task, 'alice', self.dispatch)) as (tx, rx):
                    await initialize(tx, rx)
                    response = await exchange(tx, rx, 'tools/call', 1, {'name': 'inbox', 'arguments': {}, '_meta': 'PRIVATE_METADATA_SENTINEL'})
                    self.assertIn('error', response)
                    await tx.send(message('notifications/cancelled', params={'requestId': {}, 'reason': 'PRIVATE_NOTIFICATION_SENTINEL'}))
                    await exchange(tx, rx, 'ping', 2)
                    self.assertEqual(self.calls, [])
                self.assertNotIn('PRIVATE_METADATA_SENTINEL', log.getvalue())
                self.assertNotIn('PRIVATE_NOTIFICATION_SENTINEL', log.getvalue())
            finally:
                logging.getLogger().removeHandler(handler)
        self.run_async(run)

    def test_depth_and_size_limits_prevent_dispatch(self):
        async def run():
            async with peer(ProposalMCPAdapter(self.task, 'alice', self.dispatch)) as (tx, rx):
                await initialize(tx, rx)
                deep = {}
                for _ in range(35):
                    deep = {'nested': deep}
                for n, metadata in enumerate((deep, {'large': 'x' * 17000})):
                    result = await exchange(tx, rx, 'tools/call', n, {'name': 'inbox', 'arguments': {}, '_meta': metadata})
                    self.assertIn('error', result)
                self.assertEqual(self.calls, [])
        self.run_async(run)

    def test_concurrent_duplicate_calls_execute_once(self):
        async def run():
            async with peer(ProposalMCPAdapter(self.task, 'alice', self.dispatch)) as (tx, rx):
                await initialize(tx, rx)
                call = message('tools/call', 'duplicate', {'name': 'inbox', 'arguments': {}})
                async with anyio.create_task_group() as group:
                    group.start_soon(tx.send, call)
                    group.start_soon(tx.send, call)
                with anyio.fail_after(3):
                    responses = [(await rx.receive()).message.model_dump(mode='json') for _ in range(2)]
                self.assertEqual(sum('result' in r for r in responses), 1)
                self.assertEqual(sum('error' in r for r in responses), 1)
                self.assertEqual(self.calls, [{'method': 'inbox'}])
        self.run_async(run)

    def test_cancellation_after_commit_never_replays_and_closes_binding(self):
        async def run():
            committed = anyio.Event()
            def dispatch(command):
                value = self.dispatch(command)
                committed.set()
                return value
            adapter = ProposalMCPAdapter(self.task, 'alice', dispatch)
            tx, rx = anyio.create_memory_object_stream(0)
            out, responses = anyio.create_memory_object_stream(0)
            try:
                async with anyio.create_task_group() as group:
                    group.start_soon(adapter.run, rx, out)
                    await initialize(tx, responses)
                    await tx.send(message('tools/call', 'commit', {'name': 'propose', 'arguments': {'proposal_id': 'test', 'envelope': self.envelope}}))
                    with anyio.fail_after(3):
                        await committed.wait()
                    # No response consumer: cancellation tears down after the
                    # callback's committed effect, before client acknowledgement.
                    group.cancel_scope.cancel()
                self.assertEqual(len(self.calls), 1)
                self.assertTrue(adapter._binding.application_call('inbox', {})['isError'])
                self.assertEqual(len(self.calls), 1)
                with self.assertRaises(RuntimeError):
                    await adapter.run(rx, out)
            finally:
                for stream in (tx, rx, out, responses):
                    await stream.aclose()
        self.run_async(run)

    def test_unknown_tool_name_is_not_echoed_in_diagnostics(self):
        async def run():
            log = io.StringIO()
            handler = logging.StreamHandler(log)
            logging.getLogger().addHandler(handler)
            try:
                async with peer(ProposalMCPAdapter(self.task, 'alice', self.dispatch)) as (tx, rx):
                    await initialize(tx, rx)
                    response = await exchange(tx, rx, 'tools/call', 1, {'name': 'PRIVATE_TOOL_NAME_SENTINEL', 'arguments': {}})
                    self.assertTrue('error' in response or response['result']['isError'])
                    self.assertEqual(self.calls, [])
                self.assertNotIn('PRIVATE_TOOL_NAME_SENTINEL', log.getvalue())
            finally:
                logging.getLogger().removeHandler(handler)
        self.run_async(run)

    def test_session_budgets_and_invalid_ids_terminate_without_dispatch(self):
        from unittest.mock import patch
        async def run():
            for mode in ('requests', 'messages', 'oversize-ascii', 'oversize-unicode', 'invalid-unicode'):
                adapter = ProposalMCPAdapter(self.task, 'alice', self.dispatch)
                tx, rx = anyio.create_memory_object_stream(8)
                out, responses = anyio.create_memory_object_stream(8)
                finished = anyio.Event()
                async def serve():
                    await adapter.run(rx, out)
                    finished.set()
                try:
                    with patch('mcp_proposal_adapter.MAX_REQUESTS', 1 if mode == 'requests' else 1024), patch('mcp_proposal_adapter.MAX_MESSAGES', 2 if mode == 'messages' else 2048):
                        async with anyio.create_task_group() as group:
                            group.start_soon(serve)
                            await initialize(tx, responses)
                            ident = {'oversize-ascii': 'x' * 257, 'oversize-unicode': '🙂' * 65, 'invalid-unicode': '\ud800'}.get(mode, 'call')
                            await tx.send(message('tools/call', ident, {'name': 'inbox', 'arguments': {}}))
                            with anyio.fail_after(3):
                                await finished.wait()
                            self.assertEqual(self.calls, [])
                            self.assertTrue(adapter._binding.application_call('inbox', {})['isError'])
                finally:
                    for stream in (tx, rx, out, responses):
                        await stream.aclose()
        self.run_async(run)

    def test_tools_require_initialize_and_initialized_notification(self):
        async def run():
            async with peer(ProposalMCPAdapter(self.task, 'alice', self.dispatch)) as (tx, rx):
                params = {'name': 'inbox', 'arguments': {}}
                self.assertIn('error', await exchange(tx, rx, 'tools/call', 1, params))
                await exchange(tx, rx, 'initialize', 'init', {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'peer', 'version': '1'}})
                self.assertIn('error', await exchange(tx, rx, 'tools/call', 2, params))
                await tx.send(message('notifications/initialized'))
                self.assertFalse((await exchange(tx, rx, 'tools/call', 3, params))['result']['isError'])
                self.assertEqual(self.calls, [{'method': 'inbox'}])
        self.run_async(run)


    def test_unicode_uri_and_empty_rpc_ids_correlate_without_widening_application_ids(self):
        async def run():
            async with peer(ProposalMCPAdapter(self.task, 'alice', self.dispatch)) as (tx, rx):
                await initialize(tx, rx)
                identifiers = ('', 'urn:request/1?part=a#section', '请求/🙂', 'x' * 256, '🙂' * 64)
                for ident in identifiers:
                    response = await exchange(tx, rx, 'tools/call', ident, {'name': 'inbox', 'arguments': {}})
                    self.assertEqual(response['id'], ident)
                    self.assertFalse(response['result']['isError'])
                    duplicate = await exchange(tx, rx, 'tools/call', ident, {'name': 'inbox', 'arguments': {}})
                    self.assertEqual(duplicate['id'], ident)
                    self.assertIn('error', duplicate)
                self.assertEqual(len(self.calls), len(identifiers))
                for n, ident in enumerate(('', 'urn:proposal/1', '提案', 'x' * 65)):
                    response = await exchange(tx, rx, 'tools/call', n, {'name': 'proposal_status', 'arguments': {'proposal_id': ident}})
                    self.assertTrue(response['result']['isError'])
                self.assertEqual(len(self.calls), len(identifiers))
        self.run_async(run)
