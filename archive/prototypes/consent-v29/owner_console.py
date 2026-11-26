"""Interactive offline owner inbox, with explicit review, sending and receipt checks.

One trusted operator selects fictional owner roles. This is NOT authenticated UI.
No web server, real account, external agent or calendar is used. Keys are disposable
fixture data held only in the existing signer/executor processes.
"""
import argparse
import json
import tempfile
from workflow_scenarios import fixture_scope
from fixture_ipc import JsonProcess
from network import Denied, digest


def run(simulate=False, scenario='normal', workflow='meeting', task_fixture=None):
    meeting,_=fixture_scope(workflow, task_fixture)
    fixture_args=() if task_fixture is None else ('--task-fixture',task_fixture)
    signers,executor={},None
    print('V6 OWNER INBOX | OFFLINE FICTIONAL FIXTURE')
    print('One trusted console operator controls all roles. No real-person authentication.')
    print('This console is disposable: quitting discards its temporary records and fixture keys. Deferral lasts only while this console stays open.')
    print('SIMULATED choices.' if simulate else 'Review, approve, defer or decline each request. Back/quit grants no approval.')
    fault_done=False;defer_done=False
    def confirm(phrase):return phrase if simulate else input(f"Type '{phrase}' to confirm, or anything else to stop: ")
    with tempfile.TemporaryDirectory(prefix='owner-inbox-fixture-') as directory:
        try:
            roots={};bindings={}
            for owner in meeting.participants:
                signer=JsonProcess('owner_fixture_process.py','--owner',owner,'--workflow',workflow,*fixture_args)
                signers[owner]=signer;roots[owner]=signer.read()['public_key']
            executor=JsonProcess('encrypted_executor_process.py','--state-directory',directory,'--owner-workflow','--workflow',workflow,*fixture_args)
            setup=executor.request({'owner_roots':roots})
            if not setup.get('ready_for_bindings'):raise Denied('Fixture setup failed')
            for owner,pending in setup['requests'].items():
                body=pending['binding']
                print(f"Bind fictional {owner} to transport {body['transport_pubkey']} for {workflow} {meeting.id}; receive from {', '.join(body['receive_from'])}.")
                response=signers[owner].request({'binding_request':pending,'confirmation':confirm(f'BIND {owner} {digest(pending)}')})
                if not response.get('ok'):raise Denied(response.get('error','Binding declined'))
                bindings[owner]=response['binding']
            if not executor.request({'bindings':bindings}).get('ready'):raise Denied('Executor refused identities')
            for signer in signers.values():
                if not signer.request({'registry':{'owner_roots':roots,'bindings':bindings}}).get('registry_verified'):
                    raise Denied('Signer refused identities')
            def command(method,**kwargs):
                response=executor.request({'method':method,**kwargs})
                if not response.get('ok'):raise Denied(response.get('error','Workflow command refused'))
                return response['result']
            def withdraw(card):
                owner,nonce=card['owner'],card['request_id']
                prepared=command('withdrawal_prepare',owner=owner,request_id=nonce,review_digest=card['review_digest'])
                if prepared.get('already_withdrawn'):return prepared['card']
                body=prepared['withdrawal']
                signed=signers[owner].request({'withdrawal':body,'original':prepared['original'],
                    'confirmation':f'WITHDRAW {owner} {nonce} {digest(body)}'})
                if not signed.get('ok'):raise Denied(signed.get('error','Owner withdrawal refused'))
                return command('withdrawal_commit',signed=signed['signed'])
            current=None
            while True:
                if current is None:
                    current=command('workflow_next')
                if current['kind'] in ('complete','stopped'):
                    print(current['reason']);break
                if current['kind']=='request':
                    card=current['card'];owner=card['owner'];nonce=card['request_id']
                    card=command('request_review',owner=owner,request_id=nonce)
                    print(f"\nOWNER: {owner} | REQUEST: {nonce} | {card['state']}")
                    print(card['review'])
                    if card['reason']:print('Cannot approve:',card['reason'])
                    if card['state']=='withdrawn':
                        print('Unused authorization permanently withdrawn. No delivery was queued by it; nothing was recalled.')
                        if card.get('withdrawn_successor'):
                            current={'kind':'request','card':command('request_review',owner=owner,request_id=card['withdrawn_successor'])};continue
                        if simulate or not card.get('can_prepare_fresh'):
                            if card.get('fresh_review_blocker'):print('Fresh review blocked:',card['fresh_review_blocker'])
                            break
                        if confirm(f'REVIEW {owner}')!=f'REVIEW {owner}':break
                        current={'kind':'request','card':command('withdrawal_fresh',owner=owner,request_id=nonce,review_digest=card['review_digest'])};continue
                    if card['stored_state']=='declined':
                        print('This request was declined. The guide will not replace it or ask again.');break
                    if card['state']=='superseded':
                        current={'kind':'request','card':command('request_review',owner=owner,request_id=card['replaced_by'])}
                        print('Opened the explicit replacement. No approval was carried forward.');continue
                    if card['state'] in ('expired','stale'):
                        print('This review is no longer usable. No approval is renewed automatically.')
                        if card.get('can_withdraw') and not simulate:
                            print('This authorization is unused. Withdrawal signs and applies a permanent execution block; it creates no fresh approval.')
                            if confirm(f'WITHDRAW {owner}')!=f'WITHDRAW {owner}':break
                            current={'kind':'request','card':withdraw(card)};continue
                        if card.get('pairing_reviews') and not simulate:
                            for direction in card['pairing_reviews']:
                                print(f"Missing pairing: {direction['owner']} to {direction['peer']} ({direction['state']}).")
                            choice=input('Owner whose separate pairing review to open, or anything else to stop: ').strip()
                            if choice not in [d['owner'] for d in card['pairing_reviews']]:break
                            if confirm(f'REVIEW PAIR {choice}')!=f'REVIEW PAIR {choice}':break
                            pairing=command('request_pairing',owner=owner,request_id=nonce,review_digest=card['review_digest'],direction_owner=choice)
                            current={'kind':'request','card':pairing};continue
                        if simulate or not card['can_replace']:
                            if card.get('replacement_blocker'):print('Replacement blocked:',card['replacement_blocker'])
                            break
                        phrase=f'REVIEW {owner}'
                        if input(f"Type '{phrase}' to prepare a new unsigned review, or anything else to stop: ")!=phrase:break
                        replacement=command('request_replace',owner=owner,request_id=nonce,review_digest=card['review_digest'])
                        current={'kind':'request','card':replacement};continue
                    if card['stored_state']=='deferred':
                        resume='resume' if simulate else input('Request paused. Resume review / back / quit (resume, back, quit): ').strip().lower()
                        if resume=='quit':break
                        if resume!='resume':
                            print('Request remains deferred. No approval or send occurred.')
                            if resume=='back':
                                print(json.dumps(command('request_list',owner=owner),sort_keys=True))
                            continue
                        print('Explicitly resumed deferred review. No approval inferred.')
                    if card['stored_state']=='authorized':
                        choice='submit' if simulate else input('Submit approved request / withdraw unused authorization / back / quit (submit, withdraw, back, quit): ').strip().lower()
                        if choice=='submit':command('request_submit',owner=owner,request_id=nonce);current=None;continue
                        if choice=='withdraw' and card.get('can_withdraw'):
                            print('Withdrawal signs and applies a permanent execution block. It does not create a fresh approval.')
                            if confirm(f'WITHDRAW {owner}')!=f'WITHDRAW {owner}':break
                            current={'kind':'request','card':withdraw(card)};continue
                    else:
                        if simulate:
                            if scenario=='decline' and card['action']=='send':choice='decline'
                            elif scenario=='defer' and not defer_done:choice='defer';defer_done=True
                            else:choice='approve'
                        else:choice=input('Approve / decline / defer / back / list / quit: ').strip().lower()
                        if choice in ('decline','defer'):
                            command('request_resolve',owner=owner,request_id=nonce,review_digest=card['review_digest'],choice=choice)
                            print('Request '+('declined. No approval created.' if choice=='decline' else 'deferred. Previous review token invalidated.'))
                            current=None;continue
                        if choice=='approve':
                            d=card['decision']
                            signed=signers[owner].request({'decision':d,'envelope':card['envelope'],
                                'confirmation':confirm(f"APPROVE {owner} {d['action']} {nonce}")})
                            if not signed.get('ok'):raise Denied(signed.get('error','Owner did not approve'))
                            command('request_resolve',owner=owner,request_id=nonce,review_digest=card['review_digest'],choice='approve',signed=signed['signed'])
                            print('Owner signature saved. This alone did not execute or dispatch anything.')
                            # Stay on a linked pairing review so its separately
                            # authorized submission is reachable before the guide
                            # returns to the older blocked send.
                            current={'kind':'request','card':card} if card.get('pairing_sources') else None;continue
                        if choice=='list':
                            print(json.dumps(command('request_list',owner=owner),sort_keys=True));continue
                else:
                    owner=current['owner'];nonce=current['delivery_id']
                    status=command('delivery_view',owner=owner,request_id=nonce)
                    print(f"\nDELIVERY: {nonce} | {status['label']} | attempts: {status['attempts']}")
                    if current.get('cancelled'):print(('Task' if workflow == 'generic' else 'Meeting')+' cancelled. Existing receipt checks may still establish what arrived; no new delivery is permitted.')
                    if status.get('attempt_blocker'):print('New attempt blocked:',status['attempt_blocker'])
                    if simulate:
                        if status['state']=='queued':choice='send'
                        elif status['state'] in ('dispatched','stopped_uncertain'):choice='check'
                        elif status['state']=='received':choice='process'
                        else:break
                    else:choice=input('Send attempt / check receipt / process received / back / cancel / quit (send, check, process): ').strip().lower()
                    if choice=='send':
                        if not status['can_start_attempt']:
                            print('No new attempt is permitted. Check any existing receipt or quit.');continue
                        method='delivery_attempt'
                        if simulate and not fault_done and scenario in ('lost-receipt','uncertain'):
                            method='fixture_lose_ack' if scenario=='lost-receipt' else 'fixture_fail_before_receipt';fault_done=True
                        command(method,owner=owner,request_id=nonce);current=None;continue
                    if choice=='check':
                        recovered=command('delivery_check',owner=owner,request_id=nonce)
                        print('Receipt check only:',recovered['label'],'| attempts:',recovered['attempts'])
                        if simulate and recovered['state'] in ('dispatched','stopped_uncertain'):
                            print('Still uncertain. No automatic retry, replacement request or processing.');break
                        current=None;continue
                    if choice=='process':
                        if not status['can_process']:
                            print('Cannot process without a verified unprocessed receipt. Nothing changed.');continue
                        command('delivery_process',owner=owner,request_id=nonce);current=None;continue
                    if choice=='cancel':
                        card=command('request_prepare',owner=owner,action='cancel')
                        current={'kind':'request','card':card};continue
                if choice=='quit':break
                if choice=='back':
                    print('Returned to inbox. No decision or send occurred.')
                    if not simulate:
                        print('Owners: '+', '.join(meeting.participants))
                        browse=input('Owner to list, next to continue, or quit: ').strip().lower()
                        if browse=='quit':break
                        if browse in meeting.participants:print(json.dumps(command('request_list',owner=browse),sort_keys=True))
                    current=None
                else:print('Choose one of the displayed actions. Nothing changed.')
            print('Final summary:',json.dumps(command('summary'),sort_keys=True))
            print('No live message, persistent credential, calendar action or publication occurred.')
            print('Closing this disposable console discards its records; there is no later inbox resume or identity recovery.')
        finally:
            if executor:executor.close()
            for signer in signers.values():signer.close()
            print('Fixture processes stopped. Disposable keys discarded.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate',action='store_true')
    parser.add_argument('--scenario',choices=('normal','decline','defer','lost-receipt','uncertain'),default='normal')
    parser.add_argument('--workflow',choices=('meeting','generic'),default='meeting')
    parser.add_argument('--task-fixture',choices=('garden','astronomy'))
    args=parser.parse_args()
    if not args.simulate and args.scenario!='normal':parser.error('Fault scenarios require explicit --simulate')
    try:run(args.simulate,args.scenario,args.workflow,args.task_fixture)
    except (Denied,EOFError,KeyboardInterrupt) as exc:print('Stopped safely:',str(exc))


if __name__=='__main__':main()
