"""Trusted disposable two-task workspace, not an adapter or authenticated host.

Every routed operation captures selector AND exact context. Services never share
keys, stores, signers or executors. Occupied slots cannot be reused this lifetime.
Only a RestrictedHostSession.handle callback may cross the adapter boundary.
"""
import threading
from task_fixtures import SELECTORS, fixture
from generic_protocol import task_context_digest
from network import Denied
from relationship_workspace import RelationshipWorkspace, AFTER_STOP_ACTIONS, AFTER_STOP_AGENT_METHODS
from owner_ui_service import OwnerUIService
from restricted_host_protocol import RestrictedHostSession


class OwnerWorkspace:
    def __init__(self, *, continuity=False):
        self._lock = threading.RLock()
        self._slots = {}
        self._custom = {}
        self.closed = False
        self._relationships = RelationshipWorkspace(self._scope)
        if type(continuity) is not bool: raise Denied('Expected explicit continuity option')
        from continuity_workspace import ContinuityWorkspace
        self._continuity = ContinuityWorkspace(self) if continuity else None

    def _continuity_enabled(self):
        if self._continuity is None: raise Denied('Fictional continuity is not enabled')
        return self._continuity

    def continuity_state(self):
        with self._lock:
            return self._continuity_enabled().state()

    def continuity_preview(self, request):
        with self._lock:
            return self._continuity_enabled().preview(request)

    def continuity_commit(self, operation, review, confirmation):
        with self._lock:
            return self._continuity_enabled().commit(operation, review, confirmation)

    def _continuity_args(self, selector):
        return {} if self._continuity is None else {'continuity_incarnation':self._continuity.incarnation,
                                                   'continuity_selector':selector}

    def list_tasks(self):
        with self._lock:
            rows = []
            for selector in (*SELECTORS, *self._custom):
                task = self._task(selector)
                slot = self._slots.get(selector)
                rows.append({'selector':selector,'task':task.id,'context':task_context_digest(task),
                             'requester':task.requester,'responder':task.responder,
                             'phase':slot['phase'] if slot else 'not_created',
                             'fictional':True,'temporary':True,
                             **self._relationship_status(selector, task_context_digest(task))})
            return rows

    def _relationship_status(self, selector, context):
        member = {'selector':selector, 'context':context}
        return {'local_work_stopped':self._relationships.stopped(selector, context),
                'relationship_groups':[g for g in self._relationships.groups() if member in g['members']]}

    def relationships(self):
        with self._lock:
            return self._relationships.groups()

    def relationship_preview(self, request):
        with self._lock:
            if self.closed: raise Denied('Workspace is closed')
            return self._relationships.preview(request)

    def relationship_commit(self, operation, review, confirmation):
        with self._lock:
            if self.closed: raise Denied('Workspace is closed')
            return self._relationships.commit(operation, review, confirmation)

    def _require_work(self, selector, context):
        self._scope(selector, context)
        self._relationships.require_work(selector, context)

    def _delivery_fence(self, selector, context, value):
        value = dict(value)
        stopped = self._relationships.stopped(selector, context)
        value['local_work_stopped'] = stopped
        if stopped:
            value.update(can_start_attempt=False, can_process=False,
                         attempt_blocker='Local relationship fence prevents further task work')
        return value

    def _task(self, selector):
        if type(selector) is str and selector in self._custom:
            from task_composer import composed_fixture
            return composed_fixture(self._custom[selector])[0]
        return fixture(selector)[0]

    def task_preview(self, spec):
        from task_composer import preview
        return preview(spec)

    def compose(self, spec, review_digest, confirmation):
        from task_composer import preview, MAX_CUSTOM_TASKS
        with self._lock:
            self._relationships.validate()
            checked = preview(spec)
            if type(review_digest) is not str or review_digest != checked["review_digest"] or type(confirmation) is not str or confirmation != "CREATE TASK":
                raise Denied("Review and confirm the exact custom task")
            selector = checked["selector"]
            if self.closed or selector in self._slots or selector in self._custom or len(self._custom) >= MAX_CUSTOM_TASKS:
                raise Denied("Workspace closed, custom slot occupied, or task capacity reached")
            if any(row["context"] == checked["context"] or row["task"] == checked["task"] for row in self.list_tasks()):
                raise Denied("Task identity or context already exists")
            self._custom[selector] = checked["spec"]
            slot = {"phase":"starting", "service":None}
            self._slots[selector] = slot
            try:
                slot["service"] = OwnerUIService("generic", task_spec=self._custom[selector], **self._continuity_args(selector))
                slot["phase"] = "open"
            except BaseException:
                slot["phase"] = "startup_failed_cleanup_uncertain"
                raise
            return next(row for row in self.list_tasks() if row["selector"] == selector)

    def _scope(self, selector, context):
        task = self._task(selector)
        if type(context) is not str or context != task_context_digest(task):
            raise Denied('Expected the exact selected task context')
        return task

    def create(self, selector, context):
        with self._lock:
            self._require_work(selector, context)
            if selector not in SELECTORS:
                raise Denied("Custom tasks require reviewed composition")
            if self.closed or selector in self._slots:
                raise Denied('Workspace closed or fixture slot already occupied; restart required')
            slot = {'phase':'starting','service':None}
            self._slots[selector] = slot
            try:
                slot['service'] = OwnerUIService('generic', task_fixture=selector, **self._continuity_args(selector))
                slot['phase'] = 'open'
            except BaseException:
                # Constructor performs its own best-effort cleanup. Never claim
                # success or recycle an uncertain startup incarnation.
                slot['phase'] = 'startup_failed_cleanup_uncertain'
                raise
            return self.list_tasks()[SELECTORS.index(selector)]

    def _service(self, selector, context):
        self._scope(selector, context)
        self._relationships.validate()
        slot = self._slots.get(selector)
        if self.closed or not slot or slot['phase'] != 'open':
            raise Denied('Selected fixture is not available; no replacement was created')
        return slot['service']

    def state(self, selector, context, owner):
        with self._lock:
            return {**self._service(selector, context).state(owner), **self._relationship_status(selector, context)}

    def received_messages(self, selector, context, owner):
        with self._lock:
            return self._service(selector, context).received_messages(owner)

    def response_context(self, selector, context, owner):
        with self._lock:
            return self._service(selector, context).response_context(owner)

    def review(self, selector, context, owner, request_id):
        with self._lock:
            return self._service(selector, context).review(owner, request_id)

    def delivery(self, selector, context, owner, request_id):
        with self._lock:
            return self._delivery_fence(selector, context, self._service(selector, context).delivery(owner, request_id))

    def action(self, selector, context, request):
        with self._lock:
            if type(request) is dict and request.get('action') == 'close':
                if request != {'action':'close','confirmation':'DISCARD FIXTURE'}:
                    raise Denied('Confirm discarding this exact temporary fixture')
                return self.close_task(selector, context)
            if type(request) is not dict or type(request.get('action')) is not str:
                raise Denied('Expected closed workspace action')
            if request['action'] not in AFTER_STOP_ACTIONS:
                self._require_work(selector, context)
            service = self._service(selector, context)
            result = service.action(request)
            if type(result) is dict and result.get('kind') == 'delivery':
                result = self._delivery_fence(selector, context, result)
            return result

    def proposals(self, selector, context, actor):
        with self._lock:
            service = self._service(selector, context)
            service._ready(); service._owner(actor)
            return service._command('agent_proposal_list',actor=actor)

    def import_proposal(self, selector, context, actor, proposal_id):
        with self._lock:
            self._require_work(selector, context)
            service = self._service(selector, context)
            service._ready(); service._owner(actor)
            return service._command('agent_proposal_review',actor=actor,proposal_id=proposal_id)

    def adapter(self, selector, context, actor):
        with self._lock:
            self._require_work(selector, context)
            service = self._service(selector, context)
            service._ready(); service._owner(actor)
            task = self._scope(selector, context)
            def dispatch(command):
                with self._lock:
                    if type(command) is not dict or command.get('method') not in AFTER_STOP_AGENT_METHODS:
                        self._require_work(selector, context)
                    current = self._service(selector, context)
                    if current is not service:
                        raise Denied('Original fixture incarnation is unavailable')
                    with service.lock:
                        service._ready()
                        return service._command('fixture_agent_call',actor=actor,command=command)
            return RestrictedHostSession(task, actor, dispatch)

    def reopen_storage(self, selector, context):
        """Trusted fixture storage reopen only. No restart or lost-key recovery."""
        with self._lock:
            self._require_work(selector, context)
            service = self._service(selector, context)
            service._ready()
            return service._command('reopen_storage')

    def close_task(self, selector, context):
        with self._lock:
            self._scope(selector, context)
            slot = self._slots.get(selector)
            if slot is None:
                raise Denied('Fixture was never created')
            if slot['phase'] == 'closed':
                return {'closed':True}
            slot['phase'] = 'cleanup_uncertain'
            if slot['service'] is None:
                raise RuntimeError('Startup cleanup outcome remains uncertain; slot cannot be reused')
            slot['service'].close()
            slot['phase'] = 'closed'
            return {'closed':True}

    def close(self):
        with self._lock:
            self.closed = True
            failures = []
            if self._continuity is not None:
                try:self._continuity.close()
                except Exception:failures.append('continuity')
            for selector in tuple(self._slots):
                try:
                    self.close_task(selector, task_context_digest(self._task(selector)))
                except Exception:
                    failures.append(selector)
            if failures:
                raise RuntimeError('Workspace blocked; cleanup uncertain for: '+', '.join(failures))
