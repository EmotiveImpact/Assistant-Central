"""Trusted local browser adapter for fictional owner processes, never real accounts.

No signing keys enter this process. Explicit UI choices are translated to exact
existing signer confirmations. This is not an authenticated multi-user service.
"""
import threading
import tempfile
from workflow_scenarios import fixture_scope
from fixture_ipc import JsonProcess
from network import Denied, digest


class OwnerUIService:
    def __init__(self, workflow="meeting", task_fixture=None, task_spec=None, continuity_incarnation=None, continuity_selector=None):
        scope, _ = fixture_scope(workflow, task_fixture, task_spec)
        self.workflow = workflow
        self.task_fixture = task_fixture
        self.response_composer = task_spec is not None
        fixture_args = () if task_fixture is None else ('--task-fixture', task_fixture)
        if task_spec is not None:
            from task_composer import validate_spec
            from network import canonical
            fixture_args = ('--task-spec', canonical(validate_spec(task_spec)))
        continuity_args = () if continuity_incarnation is None else ('--continuity-incarnation', continuity_incarnation, '--continuity-selector', continuity_selector)
        response_options = {'max_response_bytes':65536} if task_spec is not None else {}
        self.lock = threading.RLock()
        self.directory = tempfile.TemporaryDirectory(prefix='owner-browser-fixture-')
        self.signers, self.executor, self.roots, self.bindings = {}, None, {}, {}
        self.meeting = scope
        self.phase, self.closed = 'bindings', False
        try:
            for owner in self.meeting.participants:
                signer = JsonProcess('owner_fixture_process.py','--owner',owner,'--workflow',workflow,*fixture_args,*continuity_args,**response_options)
                self.signers[owner] = signer
                self.roots[owner] = signer.read()['public_key']
            self.executor = JsonProcess('encrypted_executor_process.py','--state-directory',self.directory.name,'--owner-workflow','--workflow',workflow,*fixture_args,**response_options)
            setup = self.executor.request({'owner_roots':self.roots})
            if not setup.get('ready_for_bindings'): raise Denied('Local fixture could not prepare public identity bindings')
            self.requests = setup['requests']
        except BaseException:
            self.close(); raise

    def close(self):
        with self.lock:
            if self.phase=='closed':return
            self.closed = True  # Fail closed to further actions before cleanup.
            errors=[]
            for child in ([self.executor] if self.executor else [])+list(self.signers.values()):
                try:child.close()
                except Exception:
                    # A broken pipe while closing stdin must not strand another
                    # signer. Independently terminate this owned fixture child.
                    process=getattr(child,'process',None)
                    try:
                        if process is None:raise RuntimeError('No child process handle')
                        if process.poll() is None:process.kill()
                        process.wait(timeout=5)
                        for stream in (process.stdin,process.stdout,process.stderr):
                            if stream is not None and not stream.closed:
                                try:stream.close()
                                except OSError:pass
                    except Exception:errors.append('child shutdown')
            try:self.directory.cleanup()
            except Exception:errors.append('temporary records cleanup')
            self.phase = 'cleanup_uncertain' if errors else 'closed'
            if errors:raise RuntimeError('Fixture actions are blocked, but cleanup was incomplete; stop the launcher and check its temporary state')

    def _owner(self, owner):
        if type(owner) is not str or owner not in self.meeting.participants:
            raise Denied('Choose an enrolled fictional owner')

    def _ready(self):
        if self.closed or self.phase!='ready':raise Denied('Approve all fictional transport bindings before using the inbox')

    def _command(self, method, **fields):
        result = self.executor.request({'method':method,**fields})
        if not result.get('ok'):raise Denied(result.get('error','Local workflow command refused'))
        return result['result']

    def state(self, owner):
        with self.lock:
            self._owner(owner)
            result={'phase':self.phase,'owner':owner,'owners':list(self.meeting.participants),
                    'meeting':self.meeting.id,'fictional':True,'temporary':True}
            if self.workflow == 'generic':
                result.pop('meeting')
                result.update(workflow='generic', task=self.meeting.id)
            if self.response_composer: result['response_composer'] = True
            if self.phase=='bindings':
                result['bindings']=[{'owner':o,'approved':o in self.bindings,'digest':digest(request),
                                     **request['binding']} for o,request in self.requests.items()]
            elif self.phase=='ready':
                result['inbox']=self._command('request_list',owner=owner)
                result['summary']=self._command('summary')
            return result

    def review(self, owner, request_id):
        with self.lock:
            self._ready();self._owner(owner)
            return self._command('request_review',owner=owner,request_id=request_id)

    def delivery(self, owner, request_id):
        with self.lock:
            self._ready();self._owner(owner)
            return self._command('delivery_view',owner=owner,request_id=request_id)

    def received_messages(self, owner):
        with self.lock:
            self._ready(); self._owner(owner)
            if self.workflow != 'generic': raise Denied('Received-message view requires a generic task')
            return self._command('received_messages',owner=owner)

    def response_context(self, owner):
        with self.lock:
            self._ready(); self._owner(owner)
            if not self.response_composer: raise Denied('Response composition requires a custom task')
            return self._command('response_context',owner=owner)

    def action(self, request):
        with self.lock:
            if type(request) is not dict or type(request.get('action')) is not str:
                raise Denied('Expected a closed local UI action')
            action=request['action']
            if self.closed and action!='close':raise Denied('Fixture actions are blocked; close it or inspect cleanup status')
            layouts={
                'bind':{'owner','binding_digest','confirmation'},
                'preview_response':{'owner','request_digest','payload'},
                'prepare_response':{'owner','request_digest','payload','preview_digest','confirmation'},
                'next':set(), 'close':{'confirmation'},
                'approve':{'owner','request_id','review_digest','confirmation'},
                'replace_review':{'owner','request_id','review_digest','confirmation'},
                'review_pairing':{'owner','request_id','review_digest','direction_owner','confirmation'},
                'withdraw_unused':{'owner','request_id','review_digest','confirmation'},
                'fresh_after_withdrawal':{'owner','request_id','review_digest','confirmation'},
                'decline':{'owner','request_id','review_digest'},
                'defer':{'owner','request_id','review_digest'},
                'submit':{'owner','request_id'}, 'recover':{'owner','request_id'},
                'check':{'owner','request_id'}, 'attempt':{'owner','request_id','confirmation'},
                'process':{'owner','request_id'}, 'cancel':{'owner'}, 'revoke':{'owner','peer'}
            }
            if action not in layouts or set(request)!={'action'}|layouts[action]:
                raise Denied('Unknown action or unexpected UI fields')
            if action=='close':
                if request['confirmation']!='DISCARD FIXTURE':raise Denied('Confirm discarding this temporary fixture')
                self.close();return {'closed':True}
            if action=='bind':
                owner=request['owner'];self._owner(owner)
                if self.phase!='bindings':raise Denied('Identity setup is already finished; replacement is forbidden')
                pending=self.requests[owner]
                if request['binding_digest']!=digest(pending) or request['confirmation']!=f'BIND {owner}':
                    raise Denied('Review this exact binding and type the displayed owner phrase')
                if owner not in self.bindings:
                    response=self.signers[owner].request({'binding_request':pending,'confirmation':f'BIND {owner} {digest(pending)}'})
                    if not response.get('ok'):raise Denied(response.get('error','Binding refused'))
                    self.bindings[owner]=response['binding']
                if len(self.bindings)==len(self.meeting.participants):
                    if not self.executor.request({'bindings':self.bindings}).get('ready'):
                        raise Denied('Local executor refused the signed identity registry')
                    for signer in self.signers.values():
                        if not signer.request({'registry':{'owner_roots':self.roots,'bindings':self.bindings}}).get('registry_verified'):
                            raise Denied('Local owner signer refused the identity registry')
                    self.phase='ready'
                return {'binding_approved':owner,'phase':self.phase}
            self._ready()
            if action=='next':return self._command('workflow_next')
            owner=request['owner'];self._owner(owner)
            if action in ('cancel','revoke'):
                kwargs={'owner':owner,'action':action}
                if action=='revoke':self._owner(request['peer']);kwargs['peer']=request['peer']
                return {'kind':'request','card':self._command('request_prepare',**kwargs)}
            if action in ('preview_response','prepare_response'):
                if not self.response_composer: raise Denied('Response composition requires a custom task')
                try:
                    import json
                    if len(json.dumps(request,allow_nan=False)) > 16000: raise Denied('Response request exceeds bounded owner frame')
                except (ValueError, TypeError, RecursionError) as exc:
                    raise Denied('Expected bounded response JSON') from exc
                result = self._command(action,**{k:v for k,v in request.items() if k != 'action'})
                return {'kind':'request','card':result} if action == 'prepare_response' else result
            nonce=request['request_id']
            if action=='withdraw_unused':
                if request['confirmation']!=f'WITHDRAW {owner}':raise Denied('Confirm permanently withdrawing this unused authorization')
                prepared=self._command('withdrawal_prepare',owner=owner,request_id=nonce,review_digest=request['review_digest'])
                if prepared.get('already_withdrawn'):return {'kind':'request','card':prepared['card']}
                withdrawal=prepared['withdrawal']
                response=self.signers[owner].request({'withdrawal':withdrawal,'original':prepared['original'],
                    'confirmation':f"WITHDRAW {owner} {nonce} {digest(withdrawal)}"})
                if not response.get('ok'):raise Denied(response.get('error','Owner signer refused withdrawal'))
                return {'kind':'request','card':self._command('withdrawal_commit',signed=response['signed'])}
            if action=='fresh_after_withdrawal':
                if request['confirmation']!=f'REVIEW {owner}':raise Denied('Confirm preparing a separate fresh unsigned review')
                return {'kind':'request','card':self._command('withdrawal_fresh',owner=owner,request_id=nonce,review_digest=request['review_digest'])}
            if action=='review_pairing':
                direction=request['direction_owner'];self._owner(direction)
                if request['confirmation']!=f'REVIEW PAIR {direction}':raise Denied('Confirm opening this owner\'s separate pairing review')
                return {'kind':'request','card':self._command('request_pairing',owner=owner,request_id=nonce,
                        review_digest=request['review_digest'],direction_owner=direction)}
            if action=='replace_review':
                if request['confirmation']!=f'REVIEW {owner}':raise Denied('Confirm preparing a new unsigned review for this owner')
                return {'kind':'request','card':self._command('request_replace',owner=owner,request_id=nonce,review_digest=request['review_digest'])}
            if action in ('approve','decline','defer'):
                card=self.review(owner,nonce)
                if request['review_digest']!=card['review_digest']:
                    raise Denied('This review changed. Refresh it and review again; nothing was approved')
                kwargs={'owner':owner,'request_id':nonce,'review_digest':request['review_digest'],'choice':action}
                if action=='approve':
                    if request['confirmation']!=f'APPROVE {owner}':raise Denied('Type the displayed owner approval phrase')
                    if card['state'] not in ('pending','deferred'):
                        raise Denied('This request is not currently approvable')
                    decision=card['decision']
                    response=self.signers[owner].request({'decision':decision,'envelope':card['envelope'],
                        'confirmation':f"APPROVE {owner} {decision['action']} {nonce}"})
                    if not response.get('ok'):raise Denied(response.get('error','Owner signer refused'))
                    kwargs['signed']=response['signed']
                return {'kind':'request','card':self._command('request_resolve',**kwargs)}
            methods={'submit':'request_submit','recover':'request_recover','check':'delivery_check',
                     'attempt':'delivery_attempt','process':'delivery_process'}
            if action=='attempt':
                if request['confirmation']!=f'SEND {owner}':raise Denied('Confirm the exact approved delivery attempt')
                status=self.delivery(owner,nonce)
                if not status['can_start_attempt']:raise Denied(status.get('attempt_blocker') or 'No new attempt is permitted')
            if action=='process' and not self.delivery(owner,nonce)['can_process']:
                raise Denied('No verified unprocessed receipt exists. Nothing was processed')
            result=self._command(methods[action],owner=owner,request_id=nonce)
            return {'kind':'request','card':result} if action in ('submit','recover') else {'kind':'delivery','owner':owner,**result}
