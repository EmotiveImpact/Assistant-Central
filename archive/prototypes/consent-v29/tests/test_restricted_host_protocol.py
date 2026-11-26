"""Local wire-profile proof only. No actual provider/native-host integration."""
import copy
import json
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from generic_demo import fixture
from network import Denied, digest
from restricted_host_protocol import RestrictedHostSession, MAX_INPUT, MAX_OUTPUT, PROTOCOL_VERSION
import test_agent_proposals as baseline


def wire(method, request_id=1, **params):
    return json.dumps({'jsonrpc': '2.0', 'id': request_id, 'method': method, 'params': params}).encode()


def init(session, version=PROTOCOL_VERSION):
    response = json.loads(session.handle(wire('initialize', 'init', protocolVersion=version,
                            capabilities={}, clientInfo={'name': 'fictional-host', 'version': '1'})))
    session.handle(b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
    return response


class HostClient:
    def __init__(self, session):
        self.session, self.seq = session, 0
        init(session)
    def call(self, command):
        self.seq += 1
        method = command['method']
        response = json.loads(self.session.handle(wire('tools/call', self.seq, name=method,
                             arguments={k: v for k, v in command.items() if k != 'method'})))
        if 'error' in response or response['result']['isError']:
            raise Denied('Restricted host call failed')
        return json.loads(response['result']['content'][0]['text'])
    def propose(self, envelope, proposal_id='proposal-one'):
        return self.call({'method': 'propose', 'proposal_id': proposal_id, 'envelope': envelope})
    def status(self, proposal_id='proposal-one'):
        return self.call({'method': 'proposal_status', 'proposal_id': proposal_id})
    def inbox(self):
        return self.call({'method': 'inbox'})['messages']


class HostExchangeTests(baseline.AgentProposalProcessTests):
    """Run all v13 process-boundary attacks through the new wire layer too."""
    def setUp(self):
        super().setUp()
        self.alice = self.make_host('alice')
        self.bob = self.make_host('bob')
    def make_host(self, actor):
        return HostClient(RestrictedHostSession(self.task, actor,
            lambda command: self.command('fixture_agent_call', actor=actor, command=command)))

    def test_reconnect_new_rpc_ids_preserve_declined_proposal_history(self):
        card = self.resolve(self.staged(), 'decline')
        self.alice.session.close()
        self.alice = self.make_host('alice')
        self.assertEqual(self.alice.propose(self.request, 'new-alias')['state'], 'declined')
        self.assertEqual(self.owner_review(proposal_id='new-alias')['request_id'], card['request_id'])
        self.assertEqual(self.command('summary')['receiver_receipts'], 0)

    def test_reconnect_preserves_withdrawn_proposal_and_no_owner_data(self):
        card = self.resolve(self.staged())
        self.service.action({'action': 'withdraw_unused', 'owner': 'alice', 'request_id': card['request_id'],
            'review_digest': card['review_digest'], 'confirmation': 'WITHDRAW alice'})
        self.alice = self.make_host('alice')
        status = self.alice.propose(self.request, 'new-alias')
        self.assertEqual(status['state'], 'withdrawn')
        self.assertNotIn(card['request_id'], json.dumps(status))
        self.assertEqual(self.bob.inbox(), [])

    def test_stopped_uncertain_remains_visible_without_resend(self):
        card = self.resolve(self.staged())
        self.submit(card)
        self.delivery('fixture_fail_before_receipt', card)
        self.submit(self.resolve(self.command('request_prepare', owner='alice', action='cancel')))
        self.delivery('delivery_attempt', card)
        for _ in range(2):
            self.assertEqual(self.alice.status()['delivery_state'], 'stopped_uncertain')
            self.assertEqual(self.alice.propose(self.request, 'retry')['delivery_state'], 'stopped_uncertain')
        self.assertEqual(self.delivery('delivery_view', card)['attempts'], 1)
        self.assertEqual(self.bob.inbox(), [])
        self.assertEqual(self.command('summary')['receiver_receipts'], 0)

    def test_duplicate_rpc_id_does_not_invoke_mutation_again(self):
        data = wire('tools/call', 'request-id', name='propose', arguments={'proposal_id':'one','envelope':self.request})
        first = json.loads(self.alice.session.handle(data))
        self.assertFalse(first['result']['isError'])
        self.assertEqual(json.loads(self.alice.session.handle(data))['error']['code'], -32600)
        self.assertEqual(len(self.command('agent_proposal_list', actor='alice')), 1)
        self.assertEqual(self.command('request_list', owner='alice'), [])


class ProtocolParserTests(unittest.TestCase):
    def setUp(self):
        self.task, _, self.request, _ = fixture()
        self.calls = []
        def callback(command):
            self.calls.append(command)
            return {'messages': [], 'payload_trust': 'untrusted_inert'}
        self.session = RestrictedHostSession(self.task, 'alice', callback)
    def error(self, data, code):
        response = json.loads(self.session.handle(data))
        self.assertEqual(response['error']['code'], code, response)
        self.assertLessEqual(len(json.dumps(response)), MAX_OUTPUT)
        return response

    def test_exact_lifecycle_negotiation_and_discovery(self):
        self.error(wire('tools/list', 1), -32000)
        self.session.handle(b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
        self.error(wire('tools/list', 2), -32000)
        response = json.loads(self.session.handle(wire('initialize', 3, protocolVersion='unknown',
                             capabilities={}, clientInfo={'name':'fake','version':'1'})))
        self.assertEqual(response['result']['protocolVersion'], PROTOCOL_VERSION)
        self.assertEqual(response['result']['capabilities'], {'tools':{}})
        self.error(wire('tools/list', 4), -32000)
        self.session.handle(b'{"jsonrpc":"2.0","method":"notifications/initialized","params":{"actor":"bob"}}')
        self.error(wire('tools/list', 5), -32000)
        self.session.handle(b'{"jsonrpc":"2.0","method":"notifications/initialized"}')
        tools = json.loads(self.session.handle(wire('tools/list', 6)))['result']['tools']
        self.assertEqual([t['name'] for t in tools], ['propose','proposal_status','inbox'])
        for tool in tools:
            self.assertFalse(tool['inputSchema']['additionalProperties'])
        self.error(wire('initialize', 7), -32600)
        self.error(wire('tools/list', 8, cursor='other-task'), -32602)
        self.assertEqual(json.loads(self.session.handle(wire('ping', 9)))['result'], {})
        self.session.close()
        self.error(wire('tools/list', 10), -32000)
        self.assertEqual(self.calls, [])

    def test_notifications_never_call_tools_or_owner_methods(self):
        for initialized in (False, True):
            if initialized: init(self.session)
            for method in ('tools/call','request_submit','sign','fixture_agent_call','initialize','agent_proposal_review'):
                for params in ({}, {'name':'propose','arguments':{'proposal_id':'one','envelope':self.request}},
                               {'actor':'bob','owner':'alice','signed':'secret'}, [], None):
                    data = json.dumps({'jsonrpc':'2.0','method':method,'params':params}).encode()
                    self.assertIsNone(self.session.handle(data))
        self.assertEqual(self.calls, [])

    def test_malformed_duplicate_nonfinite_nested_unicode_and_batches(self):
        for data in (b'', b'\xff', b'{} garbage', b'{"jsonrpc":"2.0","method":"ping","id":1,"id":2}',
                     b'{"x":NaN}', b'{"x":Infinity}', b'['*2000+b']'*2000, b'x'*(MAX_INPUT+1)):
            self.error(data, -32700)
        for data in (b'[]', b'null', b'1', b'{}', b'[{"jsonrpc":"2.0","id":1,"method":"ping"}]',
                     b'{"jsonrpc":"2.0","id":1,"method":"ping","owner":"alice"}'):
            self.error(data, -32600)
        self.assertEqual(self.calls, [])

    def test_numeric_overflow_is_rejected_even_in_notifications(self):
        for number in ('1e999', '-1e999', '1E9999999', '-1E9999999'):
            self.error(('{"jsonrpc":"2.0","method":"unknown","params":{"value":' + number + '}}').encode(), -32700)
        # Finite exponent/underflow JSON is not itself malformed, but remains
        # invalid where a tool requires an integer spelling or exact fields.
        self.assertIsNone(self.session.handle(b'{"jsonrpc":"2.0","method":"unknown","params":{"value":1e-999}}'))
        self.assertEqual(self.calls, [])

    def test_invalid_ids_params_and_capacity_bound(self):
        for candidate in (None, True, False, 1.5, {}, [], '', 'x'*65, 2**64, 'secret/path'):
            self.error(wire('ping', candidate), -32600)
        with patch('restricted_host_protocol.MAX_REQUESTS', 3):
            init(self.session)
            self.error(b'{"jsonrpc":"2.0","id":1,"method":"ping","params":[]}', -32602)
            self.error(wire('ping', 1), -32600)
            self.assertEqual(json.loads(self.session.handle(wire('ping', '1')))['result'], {})
            self.error(wire('ping', 2), -32000)
        self.error(wire('ping', 3), -32000)
        self.assertEqual(self.calls, [])

    def test_strict_init_and_closed_authority_injection(self):
        for i, extra in enumerate(({'actor':'bob'}, {'owner_roots':{}}, {'task':'other'}, {'capabilities':{'sampling':{}}})):
            args = {'protocolVersion':PROTOCOL_VERSION,'capabilities':{},'clientInfo':{'name':'x','version':'1'}, **extra}
            self.error(wire('initialize', i, **args), -32602)
        init(self.session)
        for i, method in enumerate(('request_prepare','request_resolve','request_submit','dispatch','bootstrap',
                                    'sign','resources/list','prompts/get','agent_proposal_list','fixture_agent_call')):
            self.error(wire(method, 'method'+str(i)), -32601)
            self.error(wire('tools/call', 'tool'+str(i), name=method, arguments={}), -32602)
        for i, field in enumerate(('owner','actor','task','context','grant','signature','signed','method','request_id')):
            self.error(wire('tools/call', 'field'+str(i), name='inbox', arguments={field:'secret'}), -32602)
        self.assertEqual(self.calls, [])

    def test_callback_error_is_sanitized_not_retried_and_output_checked(self):
        attempts = []
        def fail(command):
            attempts.append(command)
            raise RuntimeError('SECRET owner path /private/file and recipient bob')
        session = RestrictedHostSession(self.task, 'alice', fail)
        init(session)
        data = wire('tools/call', 1, name='inbox', arguments={})
        result = session.handle(data)
        self.assertNotIn(b'SECRET', result)
        self.assertEqual(json.loads(result)['error']['code'], -32603)
        session.handle(data)
        self.assertEqual(len(attempts), 1)
        for output in ({'messages':[], 'payload_trust':'untrusted_inert', 'owner':'secret'},
                       {'messages':[{'envelope':self.request,'envelope_digest':digest(self.request)}], 'payload_trust':'untrusted_inert'},
                       {'messages':['x'*(MAX_OUTPUT+1)],'payload_trust':'untrusted_inert'}):
            session = RestrictedHostSession(self.task, 'alice', lambda command:output)
            init(session)
            result = session.handle(data)
            self.assertEqual(json.loads(result)['error']['code'], -32603)
            self.assertLess(len(result), 200)
            self.assertNotIn(b'secret', result)

    def test_denied_error_contains_no_callback_detail(self):
        def reject(command): raise Denied('SECRET recipient and owner signature')
        session = RestrictedHostSession(self.task, 'alice', reject)
        init(session)
        result = session.handle(wire('tools/call', 1, name='inbox', arguments={}))
        self.assertTrue(json.loads(result)['result']['isError'])
        self.assertNotIn(b'SECRET', result)

    def test_parallel_identical_rpc_id_invokes_callback_once(self):
        init(self.session)
        data = wire('tools/call', 1, name='inbox', arguments={})
        with ThreadPoolExecutor(max_workers=8) as pool:
            replies = list(pool.map(self.session.handle, [data]*16))
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(sum('result' in json.loads(r) for r in replies), 1)

    def test_tool_output_is_detached_and_bound_to_actor_task(self):
        init(self.session)
        result = json.loads(self.session.handle(wire('tools/list', 1)))
        result['result']['tools'][0]['inputSchema']['additionalProperties'] = True
        again = json.loads(self.session.handle(wire('tools/list', 2)))
        self.assertFalse(again['result']['tools'][0]['inputSchema']['additionalProperties'])
        for actor in ('charlie', [], None):
            with self.assertRaises(Denied): RestrictedHostSession(self.task, actor, lambda c: {})


if __name__ == '__main__': unittest.main()
