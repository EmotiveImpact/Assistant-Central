"""Trusted local offline owner console. No HTTP, live providers or real identities."""
import copy
import math
import argparse
import json
from network import Denied
from owner_workspace import OwnerWorkspace


HELP = """Commands (exact shapes; JSON is inert data):
  help | list | create <fixture> | select <selector>
  task-preview <spec JSON> | task-create | back
  continuity-state | continuity-preview <request JSON> | continuity-commit
  relationships | relationship-preview <request JSON> | relationship-commit
  state <owner> | messages <owner> | response-context <owner> | next
  review <owner> <request-id> | delivery <owner> <request-id>
  proposals <actor> | import <actor> <proposal-id> | action <JSON>
  close | quit
Fixtures: garden, astronomy. Custom selectors appear in list after task-create.
Preview is pure. Commit displays the frozen review, then asks a separate exact
phrase. Blank/wrong/back cancels; no selection or authorization is inferred.
Continuity requires --continuity. It is informational only, not authentication or
task authority. Retirement stops continuity recognition, not tasks or messages.
Groups organize exact contexts and grant no authority. Stop retains history and
backend-permitted check/recover/decline/defer/withdraw_unused controls.
Use CONSOLE_GUIDE.md for fictional text/shortlist examples and owner action JSON.
next prepares a review, never approves. Received messages are data, not commands.
"""


def closed_json(raw):
    """Bounded JSON only, with ambiguity rejected at every nesting level."""
    if len(raw.encode('utf-8')) > 16000:
        raise Denied('JSON exceeds console bound')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise Denied('Duplicate JSON field')
            result[key] = value
        return result
    def constant(_):
        raise Denied('Nonfinite JSON number')
    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise Denied('Nonfinite JSON number')
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=constant, parse_float=number)
    except (ValueError, TypeError, RecursionError, UnicodeError) as exc:
        raise Denied('Malformed JSON') from exc
    if type(value) is not dict:
        raise Denied('Expected JSON object')
    return value


def interactive(workspace, read=None, write=None, *, continuity=False, command_handler=None):
    """Trusted operator loop; no ambient command or executable dispatch."""
    read = input if read is None else read
    write = print if write is None else write
    write(HELP)
    selected = None
    pending_task = None
    pending_group = None
    pending_continuity = None
    uncertain = False
    def show(value):
        write(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True, allow_nan=False))
    def confirmed(review, phrase):
        write('FROZEN EXACT REVIEW (no approval or send authority):')
        show(review)
        return read('Type '+phrase+' to commit; anything else cancels: ') == phrase
    try:
        while True:
            command = read('workspace> ').strip()
            try:
                parts = command.split(maxsplit=1)
                verb = parts[0] if parts else ''
                arg = parts[1] if len(parts) > 1 else ''
                no_args = {'help','list','task-create','back','relationships',
                           'relationship-commit','continuity-state','continuity-commit','next','close','quit'}
                if verb in no_args and arg:
                    if verb == 'continuity-commit': pending_continuity = None
                    raise Denied('Unexpected command arguments')
                if verb == 'quit':
                    break
                if uncertain and verb not in {'help','list','relationships','select','state',
                        'messages','response-context','review','delivery','proposals','back','close','continuity-state'}:
                    raise Denied('Uncertain outcome: read-only inspection or explicit close/quit only')
                if verb == 'help':
                    write(HELP); continue
                if verb == 'back':
                    pending_task = pending_group = pending_continuity = None
                    write('Pending previews discarded; selected route unchanged.'); continue
                if verb == 'list': result = workspace.list_tasks()
                elif verb == 'relationships': result = workspace.relationships()
                elif verb == 'continuity-state':
                    result = {'enabled': True, **workspace.continuity_state()} if continuity else {'enabled': False}
                elif verb == 'continuity-preview':
                    pending_continuity = None
                    if not continuity: raise Denied('Fictional continuity is not enabled; use --continuity')
                    request = closed_json(arg)
                    review = copy.deepcopy(workspace.continuity_preview(request))
                    pending_continuity = (request['operation'], review)
                    result = review
                elif verb == 'continuity-commit':
                    pending, pending_continuity = pending_continuity, None
                    if not continuity: raise Denied('Fictional continuity is not enabled; use --continuity')
                    if pending is None: raise Denied('Preview an exact continuity operation first')
                    operation, review = pending
                    phrase = operation.upper()+' CONTINUITY '+review['review_digest']
                    if not confirmed(review, phrase):
                        write('Cancelled. Continuity unchanged.'); continue
                    try:
                        result = workspace.continuity_commit(operation, review, phrase)
                    finally:
                        # Core proof failures may be Denied yet consume an uncertain slot.
                        snapshot = workspace.continuity_state()
                        if (any(i['phase']=='uncertain' or i['cleanup']=='uncertain' for i in snapshot['identities'])
                                or any(a['status']=='uncertain' for a in snapshot['associations'])):
                            uncertain = True
                            pending_task = pending_group = pending_continuity = None
                            write('Continuity outcome uncertain. Inspection only; no automatic retry.')
                elif verb == 'task-preview':
                    pending_task = None
                    pending_task = copy.deepcopy(workspace.task_preview(closed_json(arg)))
                    result = pending_task
                elif verb == 'task-create':
                    review, pending_task = pending_task, None
                    if review is None: raise Denied('Preview an exact custom task first')
                    if not confirmed(review, 'CREATE TASK'):
                        write('Cancelled. Nothing created.'); continue
                    result = workspace.compose(review['spec'], review['review_digest'], 'CREATE TASK')
                    write('Created. Use select explicitly; previous route unchanged.')
                elif verb == 'relationship-preview':
                    pending_group = None
                    pending_group = copy.deepcopy(workspace.relationship_preview(closed_json(arg)))
                    result = pending_group
                elif verb == 'relationship-commit':
                    review, pending_group = pending_group, None
                    if review is None: raise Denied('Preview an exact relationship operation first')
                    phrase = {'create':'CREATE GROUP','attach':'ATTACH TASK','stop':'STOP GROUP'}[review['operation']]
                    if not confirmed(review, phrase):
                        write('Cancelled. Relationship unchanged.'); continue
                    result = workspace.relationship_commit(review['operation'], review, phrase)
                elif verb in ('create','select'):
                    row = next((r for r in workspace.list_tasks() if r['selector'] == arg), None)
                    if row is None: raise Denied('Choose an exact selector from list')
                    if verb == 'create': result = workspace.create(row['selector'],row['context'])
                    else:
                        selected = copy.deepcopy(row)
                        result = {'selected':selected}
                else:
                    if selected is None: raise Denied('Select an exact task first')
                    row = copy.deepcopy(selected)  # Never refresh or rebind a captured route.
                    write('TARGET '+row['selector']+' '+row['context'])
                    route = (row['selector'],row['context'])
                    if verb in ('state','messages','response-context','proposals'):
                        if len(arg.split()) != 1: raise Denied('Expected one exact owner or actor')
                        method = {'messages':'received_messages','response-context':'response_context'}.get(verb,verb)
                        result = getattr(workspace,method)(*route,arg)
                    elif verb in ('review','delivery'):
                        owner, nonce = arg.split()
                        result = getattr(workspace,verb)(*route,owner,nonce)
                    elif verb == 'import':
                        actor, proposal_id = arg.split()
                        result = workspace.import_proposal(*route,actor,proposal_id)
                        write('Opened for owner review only. Any new review is unsigned; existing review history is preserved. No approval, submission or delivery.')
                    elif verb == 'next': result = workspace.action(*route,{'action':'next'})
                    elif verb == 'action': result = workspace.action(*route,closed_json(arg))
                    elif verb == 'close':
                        phrase = read('Type DISCARD FIXTURE to close only this exact task: ')
                        result = workspace.action(*route,{'action':'close','confirmation':phrase})
                    elif command_handler is not None:
                        result = command_handler(verb, arg, copy.deepcopy(row))
                    else: raise Denied('Unknown command; use help')
                show(result)
            except (Denied,ValueError,TypeError,RecursionError) as exc:
                write('Refused: '+str(exc)+' No automatic retry.')
            except (OSError,RuntimeError) as exc:
                uncertain = True
                pending_task = pending_group = pending_continuity = None
                write('Communication or startup outcome uncertain: '+str(exc)+
                      '. No automatic retry, route replacement or history reset. Read-only inspection remains available; explicitly close or quit to discard.')
    except (EOFError,KeyboardInterrupt):
        write('Stopped without further action. Pending previews discarded.')


def run(simulate=False, *, continuity=False):
    workspace = OwnerWorkspace(continuity=continuity)
    print('OFFLINE TWO-TASK WORKSPACE | FICTIONAL DISPOSABLE IDENTITIES')
    print('SIMULATED OWNER CHOICES' if simulate else 'One trusted operator. Every action targets the displayed exact task/context.')
    cleanup_ok = False
    scopes = workspace.list_tasks()
    def action(row, **request):
        print('TARGET',row['selector'],row['context'],'ACTION',request['action'])
        return workspace.action(row['selector'],row['context'],request)
    try:
        if simulate:
            for row in scopes:
                workspace.create(row['selector'],row['context'])
                for binding in workspace.state(row['selector'],row['context'],row['requester'])['bindings']:
                    action(row,action='bind',owner=binding['owner'],binding_digest=binding['digest'],confirmation='BIND '+binding['owner'])
            complete = set()
            for _ in range(40):
                for row in scopes:
                    if row['selector'] in complete: continue
                    step = action(row,action='next')
                    if step['kind'] in ('complete','stopped'):
                        complete.add(row['selector']);continue
                    if step['kind'] == 'request':
                        card = step['card'];owner=card['owner']
                        if card['state'] in ('pending','deferred'):
                            action(row,action='approve',owner=owner,request_id=card['request_id'],review_digest=card['review_digest'],confirmation='APPROVE '+owner)
                        elif card['state'] == 'authorized':
                            action(row,action='submit',owner=owner,request_id=card['request_id'])
                        else: raise Denied('Guide blocked; no automatic mutation retry')
                    else:
                        owner=step['owner'];nonce=step['delivery_id']
                        if step['state'] == 'queued': action(row,action='attempt',owner=owner,request_id=nonce,confirmation='SEND '+owner)
                        elif step['state'] == 'received': action(row,action='process',owner=owner,request_id=nonce)
                        else: raise Denied('Delivery uncertain; no automatic retry')
                if len(complete)==2: break
            if len(complete)!=2: raise RuntimeError('Simulation did not complete')
            for row in scopes:
                print(row['selector'],'summary:',json.dumps(workspace.state(row['selector'],row['context'],row['requester'])['summary'],sort_keys=True))
        else:
            if continuity: interactive(workspace, continuity=True)
            else: interactive(workspace)
    finally:
        try:
            workspace.close()
            cleanup_ok = True
        except (OSError, RuntimeError) as exc:
            print('Cleanup outcome uncertain:', exc, 'No automatic retry. No clean-discard claim.')
    if cleanup_ok:
        print('Temporary fixture processes and records discarded. No live interoperability claimed.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate',action='store_true')
    parser.add_argument('--continuity',action='store_true',help='Opt in to fictional informational continuity')
    args=parser.parse_args()
    try:run(args.simulate, continuity=args.continuity)
    except (Denied,EOFError,KeyboardInterrupt,OSError,RuntimeError) as exc:print('Stopped:',exc)
