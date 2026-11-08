"""Synthetic in-memory r5 wire demonstration; no actual stdio/peer transport."""
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.dont_write_bytecode = True

import anyio
from integration.bootstrap import TeamWorkflow
from integration.team_proposals import BoundArtifactProposal
from team_workflow import AgentRef, TaskSpec, TeamPlan
from raw_bridge.transport import RawBridge

TEXT = 'SYNTHETIC ONLY: A reviewed garden research note for a fictional copy task.'


async def exercise(bound, calls, *, before_each=None, fragment_size=4096):
    """Bounded synthetic client using actual unchanged r3/r4 parsing and tools.

    Each call receives one reply. Notifications are used only in the fixed
    initialization sequence. Caller data never configures a provider or transport.
    """
    if type(fragment_size) is not int or not 1 <= fragment_size <= 4096:
        raise ValueError('Invalid synthetic fragment size')
    raw = RawBridge(bound.facade)
    to_server, incoming = anyio.create_memory_object_stream(32)
    outgoing, from_server = anyio.create_memory_object_stream(4)
    failures, replies = [], []

    class Reader:
        async def receive(self, limit):
            return await incoming.receive()

    class Writer:
        async def send(self, value):
            await outgoing.send(value)

    async def server():
        try:
            await raw.run(Reader(), Writer())
        except Exception as exc:
            failures.append(exc)
        finally:
            await outgoing.aclose()

    async def send(value):
        encoded = value if type(value) is bytes else (json.dumps(value, ensure_ascii=False) + '\n').encode()
        for start in range(0, len(encoded), fragment_size):
            await to_server.send(encoded[start:start + fragment_size])

    with anyio.fail_after(10):
        async with to_server, incoming, outgoing, from_server, anyio.create_task_group() as group:
            group.start_soon(server)
            await send({'jsonrpc': '2.0', 'id': 'init', 'method': 'initialize', 'params': {
                'protocolVersion': '2025-11-25', 'capabilities': {},
                'clientInfo': {'name': 'synthetic-team-client', 'version': '1'}}})
            replies.append(json.loads(await from_server.receive()))
            await send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
            for index, call in enumerate(calls):
                if before_each is not None:
                    before_each(index)
                await send(call)
                replies.append(json.loads(await from_server.receive()))
            await to_server.aclose()
    if failures:
        raise RuntimeError('Synthetic byte exercise stopped; local proposal outcome may be uncertain.') from None
    return replies


def synthetic_mapping():
    plan = TeamPlan('synthetic-wire-team', 'lead', (
        AgentRef('lead', 'alice', 'fixture-a', 'Review'),
        AgentRef('research', 'bob', 'fixture-b', 'Research'),
        AgentRef('copy', 'carol', 'fixture-c', 'Copy'),
    ), (
        TaskSpec('source', 'research', 'Produce a fictional research note', 'research'),
        TaskSpec('target', 'copy', 'Draft copy from the accepted note', 'copy', ('source',)),
    ))
    w = TeamWorkflow(':memory:', plan, clock=lambda: 1000)
    try:
        w.accept_lead('alice', expected_context=w.context)
        source = w.facade('research')
        request = source.propose_start('source', 'source-proposal')
        w.decide_start('bob', request['request_id'], request['review_digest'], 'approve',
                       expires=1100, expected_context=w.context)
        source.start(request['request_id'])
        source.submit('source', 'note-v1', TEXT)
        review = w.disclosure_review('bob', 'note-v1', 'lead', expected_context=w.context)
        w.approve_disclosure('bob', 'note-v1', 'lead', review['review_digest'], expected_context=w.context)
        w.facade('lead').review_output('source', 'note-v1', 'accept')
        review = w.disclosure_review('bob', 'note-v1', 'copy', 'target', expected_context=w.context)
        w.approve_disclosure('bob', 'note-v1', 'copy', review['review_digest'], 'target', expected_context=w.context)
        bound = BoundArtifactProposal(w, 'note-v1', 'target', expected_context=w.context)
        return w, bound
    except BaseException:
        w.close()
        raise


def main():
    from integration.run_checks import guard
    sys.addaudithook(guard)
    w, bound = synthetic_mapping()
    try:
        calls = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'propose', 'arguments': {'text': TEXT}}},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'proposal_status', 'arguments': {'proposal_id': bound.proposal_id}}},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'processed_inbox', 'arguments': {}}},
        ]
        replies = anyio.run(exercise, bound, calls)
        print(json.dumps({'simulation': True, 'actual_transport': False, 'owner_choices': 'scripted fictional choices',
                          'binding': bound.binding_review(), 'protocol_replies': replies,
                          'target_state': w._row('target')['state'],
                          'effect': 'One pending local unsigned proposal; zero releases, messages or recipient processing.'}, indent=2))
    finally:
        bound.close()
        w.close()


if __name__ == '__main__':
    main()
