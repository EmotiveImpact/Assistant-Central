"""Offline two-scripted-client handoff with separate trusted terminal owners."""
import argparse
import json
from generic_protocol import task_envelope
from network import Denied, digest
from offline_peer_pipes import Peer, node_runtime
from owner_workspace import OwnerWorkspace
from task_composer import composed_fixture
from workspace_console import interactive

SPEC = {'selector':'custom-peer', 'task_id':'peer-text', 'conversation_id':'peer-fiction',
        'requester':'alice', 'query':'Describe a fictional moon garden',
        'capability':'bounded-text-exchange-v1', 'max_reply_chars':100}
TEXT = 'The fictional moon garden glows blue.'
HELP = '''OFFLINE SCRIPTED PEERS | No provider, network, wake or continuity
One trusted operator controls both fictional owners. Clients have no owner tools.
First use task-preview with the exact specification below, then task-create and
its separate CREATE TASK confirmation. Explicitly select custom-peer.
Review and bind both fictional transport bindings with existing state/action
controls before peers-start. Additional selected-task commands:
  peers-start
  peer alice discover | peer bob discover
  peer alice propose  | peer bob propose
  peer alice status   | peer bob status
  peer alice inbox    | peer bob inbox
Launch never binds, pairs, imports, approves, submits, delivers or processes.
Use existing state/action/next controls for bindings and both pairing decisions.
Import candidates with import alice peer-alice or import bob peer-bob.
Bob's fixed result becomes eligible only after the exact request is processed.
Each peer command is one explicit step; there is no polling or automatic retry.
'''


class Demo:
    def __init__(self, workspace, *, mixed_node=None):
        if mixed_node not in (None, "alice", "bob"):
            raise ValueError("Expected mixed Node actor alice or bob")
        self.mixed_node = mixed_node
        self.workspace = workspace
        self.peers = {}
        self.route = None
        self.started = False
        self.task, _, self.request, _ = composed_fixture(SPEC)
        self.result = task_envelope(self.task, 'result', {'text':TEXT}, reply_to=digest(self.request))

    def command(self, verb, arg, selected):
        if verb not in ('peers-start','peer'):
            raise Denied('Unknown command; use help and OFFLINE_PEER_DEMO.md')
        expected = self.workspace.task_preview(SPEC)
        route = (selected['selector'], selected['context'])
        if route != (expected['selector'], expected['context']):
            raise Denied('Explicitly select the exact reviewed custom-peer task')
        if verb == 'peers-start':
            if arg or self.started:
                raise Denied('Clients can start once only; no replacement or reconnect')
            if self.mixed_node is not None:
                node_runtime()  # Preflight before any client or session is launched.
            sessions = {actor:self.workspace.adapter(*route, actor) for actor in ('alice','bob')}
            self.started = True
            self.route = route
            try:
                for actor, envelope in (('alice',self.request), ('bob',self.result)):
                    self.peers[actor] = Peer(sessions[actor], envelope, 'peer-'+actor,
                        client='node' if actor == self.mixed_node else 'python')
            except BaseException:
                for session in sessions.values():
                    session.close()
                self.close()
                raise
            return {'clients':{actor:peer.pid for actor,peer in self.peers.items()},
                    'scope':selected, 'owner_authority':False, 'scripted':True}
        parts = arg.split()
        if len(parts) != 2 or parts[0] not in ('alice','bob') or parts[1] not in ('discover','propose','status','inbox'):
            raise Denied('Expected exact peer actor and discover/propose/status/inbox')
        if route != self.route or parts[0] not in self.peers:
            raise Denied('Start fixed peers on the selected exact task first')
        return self.peers[parts[0]].step(parts[1])

    def close(self):
        errors = []
        for peer in self.peers.values():
            try:
                peer.close()
                if peer.cleanup_uncertain:
                    raise RuntimeError('Earlier client cleanup was uncertain')
            except (OSError, RuntimeError) as exc:
                errors.append(exc)
        if errors:
            raise RuntimeError('Client cleanup uncertain')


def tool_value(report):
    response = report['response']
    if 'error' in response or response['result']['isError']:
        raise Denied('Scripted peer call refused')
    return json.loads(response['result']['content'][0]['text'])


def simulate(workspace, demo, write=print):
    """Explicitly requested synthetic choices, never human approval evidence."""
    write('SIMULATED OWNER CHOICES: synthetic reproducibility only, not human consent')
    review = workspace.task_preview(SPEC)
    row = workspace.compose(SPEC, review['review_digest'], 'CREATE TASK')
    route = row['selector'], row['context']
    def action(**fields):
        write('SIMULATED OWNER DECISION '+fields['action'])
        return workspace.action(*route, fields)
    def approve_submit(card):
        action(action='approve', owner=card['owner'], request_id=card['request_id'],
               review_digest=card['review_digest'], confirmation='APPROVE '+card['owner'])
        action(action='submit', owner=card['owner'], request_id=card['request_id'])
    write('EXPLICIT SYNTHETIC TASK SELECTION '+row['selector']+' '+row['context'])
    for binding in workspace.state(*route,'alice')['bindings']:
        action(action='bind', owner=binding['owner'], binding_digest=binding['digest'], confirmation='BIND '+binding['owner'])
    write(json.dumps(demo.command('peers-start','',row), sort_keys=True))
    for actor in ('alice','bob'):
        report = demo.command('peer',actor+' discover',row)
        names = [t['name'] for t in report['response']['result']['tools']]
        if names != ['propose','proposal_status','inbox']:
            raise RuntimeError('Unexpected discovered tools')
        write('CLIENT '+actor+' discovered '+', '.join(names))
    staged = tool_value(demo.command('peer','alice propose',row))
    write('PROPOSAL ONLY '+json.dumps(staged, sort_keys=True))
    # Only the two expected pairing reviews. No generic auto-next loop over sends.
    for _ in range(2):
        step = action(action='next')
        card = step['card']
        if card['decision']['action'] != 'pair':
            raise RuntimeError('Expected pairing review; no automatic continuation')
        approve_submit(card)
    for sender, recipient in (('alice','bob'),('bob','alice')):
        if sender == 'bob':
            tool_value(demo.command('peer','bob propose',row))
            write('PROPOSAL ONLY bob fixed result')
        card = workspace.import_proposal(*route,sender,'peer-'+sender)
        # import returns the same owner review surface used by the console.
        if 'card' in card:
            card = card['card']
        write('OWNER IMPORT unsigned review')
        approve_submit(card)
        if tool_value(demo.command('peer',recipient+' inbox',row))['messages']:
            raise RuntimeError('Inbox disclosed before receipt')
        action(action='attempt',owner=sender,request_id=card['request_id'],confirmation='SEND '+sender)
        if tool_value(demo.command('peer',recipient+' inbox',row))['messages']:
            raise RuntimeError('Receipt incorrectly disclosed inbox')
        write('DELIVERY RECEIPT present; recipient processed inbox still empty')
        action(action='process',owner=sender,request_id=card['request_id'])
        inbox = tool_value(demo.command('peer',recipient+' inbox',row))['messages']
        expected = demo.request if sender == 'alice' else demo.result
        if len(inbox) != 1 or inbox[0]['envelope'] != expected:
            raise RuntimeError('Expected exact processed envelope')
        write('PROCESSING '+recipient+' inbox contains exact '+inbox[0]['envelope']['type'])
    write('OFFLINE ROUNDTRIP COMPLETE: two scripted clients, separate synthetic owner decisions')


def run(simulated=False, read=None, write=print, *, mixed_node=None):
    workspace = OwnerWorkspace()
    demo = Demo(workspace, mixed_node=mixed_node)
    try:
        if simulated:
            simulate(workspace, demo, write)
        else:
            write(HELP)
            write('task-preview '+json.dumps(SPEC, sort_keys=True))
            write('Fixed result candidate: '+TEXT)
            interactive(workspace, read=read, write=write, command_handler=demo.command)
    finally:
        try:
            demo.close()
        finally:
            workspace.close()
    write('Clients reaped; temporary workspace discarded. No live interoperability claimed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate',action='store_true',help='Explicit synthetic owner choices, not human approvals')
    parser.add_argument("--mixed-node", choices=("alice", "bob"),
                        help="Explicit offline Node 18+ actor; other actor remains Python")
    args = parser.parse_args()
    try:
        run(args.simulate, mixed_node=args.mixed_node)
    except (Denied, OSError, RuntimeError, KeyboardInterrupt, EOFError) as exc:
        print('Stopped:', str(exc), 'No automatic retry. Cleanup failure never implies clean discard.')
        raise SystemExit(1)
