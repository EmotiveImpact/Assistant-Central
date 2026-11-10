"""Explicit synthetic task -> reviewed original result -> inert return draft.

This composition never enables a network/model transport. Its deterministic
fixture is labelled synthetic at every boundary. Staging never releases content.
"""
import json

from .crypto import canonical, digest
from .provider import ResponsesAdapter, ProviderBudget, ProviderDenied
from .runtime import VERSION as RUNTIME_VERSION, RuntimeDenied, hash_id

VERSION = 'assistant-central-synthetic-workflow/1'
FIXTURE_MODEL = 'synthetic-research-v1'
FIXTURE_GRANT = {'provider': 'openai', 'model': FIXTURE_MODEL, 'max_output_tokens': 128}


class WorkflowDenied(RuntimeDenied):
    """A bounded refusal without payload or credential details."""


class _ResearchFixture:
    """No tools, network, credentials, model or factual research are performed."""
    synthetic_only = True

    def send(self, encoded):
        request = json.loads(encoded)
        if request.get('model') != FIXTURE_MODEL or request.get('max_output_tokens') != 128:
            raise WorkflowDenied('The synthetic fixture route is immutable')
        request_id = digest(request)
        # Do not echo task instructions into the result or pretend to answer them.
        output = ('SYNTHETIC FIXTURE RESULT: No model or research was run.\n'
                  'Fictional research plan: compare three imaginary community garden ideas; '
                  'record assumptions; ask the requester to review.\n'
                  'Original request commitment: ' + request_id)
        response = {'object': 'response', 'id': 'fixture-' + request_id,
                    'status': 'completed', 'error': None,
                    'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                                'content': [{'type': 'output_text', 'text': output, 'annotations': []}]}],
                    'usage': {'input_tokens': 0, 'output_tokens': 0, 'total_tokens': 0}}
        return 200, canonical(response)


class SyntheticWorkLoop:
    """Owner operations over one runtime, with an immutable fixture route/budget.

    The default permits inspection only. `enabled=True` is a trusted host choice,
    not an owner/peer HTTP field. It still cannot select any live transport.
    """
    def __init__(self, runtime, *, enabled=False):
        if type(enabled) is not bool:
            raise WorkflowDenied('Expected an explicit synthetic workflow flag')
        self.runtime, self.enabled = runtime, enabled
        self.adapter = None
        history = runtime.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='pilot_workflow_meta'").fetchone()
        if history:
            meta = runtime.db.execute('SELECT version,model FROM pilot_workflow_meta WHERE singleton=1').fetchone()
            if meta is None or tuple(meta) != (VERSION, FIXTURE_MODEL):
                raise WorkflowDenied('Unknown retained workflow version or route')
        elif not enabled:
            # Merely starting a default-disabled server must not reserve or
            # change the immutable standalone adapter budget in an old store.
            return
        self.adapter = ResponsesAdapter(runtime.db, runtime.authorise_provider,
            runtime.auth.authenticate, budget=ProviderBudget(max_requests=3, max_output_tokens=128),
            transport=_ResearchFixture() if enabled else None, allow_live=False, clock=runtime.clock)
        with self.adapter._transaction():
            runtime.db.execute('''CREATE TABLE IF NOT EXISTS pilot_workflow_meta(
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),version TEXT NOT NULL,model TEXT NOT NULL)''')
            runtime.db.execute('INSERT OR IGNORE INTO pilot_workflow_meta VALUES(1,?,?)', (VERSION, FIXTURE_MODEL))
            runtime.db.execute('''CREATE TABLE IF NOT EXISTS pilot_workflow_artifacts(
                run_id TEXT PRIMARY KEY REFERENCES pilot_provider_runs(id),
                artifact_id TEXT UNIQUE NOT NULL REFERENCES runtime_items(id),
                review_digest TEXT NOT NULL, review TEXT NOT NULL)''')

    def _enabled(self):
        if self.enabled is not True:
            raise WorkflowDenied('Synthetic workflow is disabled by the host')

    def _run(self, session, run_id):
        if self.adapter is None:
            raise WorkflowDenied('No retained synthetic workflow exists')
        try:
            row = self.adapter._get(run_id, self.adapter._identity(session))
        except (ProviderDenied, PermissionError):
            raise WorkflowDenied('Unknown or unavailable local workflow') from None
        binding = json.loads(row['binding'])
        if (run_id != 'work-' + binding['item_id']
                or {key: binding[key] for key in FIXTURE_GRANT} != FIXTURE_GRANT):
            raise WorkflowDenied('Run is not part of this exact synthetic workflow')
        hash_id(binding['item_id'])
        return row

    def _mapping(self, run_id):
        row = self.runtime.db.execute('SELECT * FROM pilot_workflow_artifacts WHERE run_id=?', (run_id,)).fetchone()
        if row:
            row = self.runtime.storage.row('pilot_workflow_artifacts', row)
            review = json.loads(row['review'])
            if (digest(review) != row['review_digest'] or review.get('run_id') != run_id
                    or review.get('artifact_id') != row['artifact_id']
                    or digest(review.get('artifact')) != row['artifact_id']):
                raise WorkflowDenied('Retained workflow mapping integrity mismatch')
            artifact, body = self.runtime._row(row['artifact_id'])
            if body != review['artifact'] or artifact['direction'] != 'outgoing':
                raise WorkflowDenied('Retained workflow artifact integrity mismatch')
        return row

    def _current_request(self, session, row):
        try:
            request = self.adapter._request(session, json.loads(row['binding']), self.adapter._identity(session))
        except (ProviderDenied, PermissionError):
            raise WorkflowDenied('Current exact task and source authority required') from None
        if canonical(request).decode() != row['request']:
            raise WorkflowDenied('Original provider request changed')

    def _result_review(self, session, row):
        if row['state'] != 'completed' or row['cancelled']:
            raise WorkflowDenied('No available original completed result')
        self._current_request(session, row)
        result = row['result']
        if type(result) is not str or digest({'text': result}) != row['result_digest']:
            raise WorkflowDenied('Retained original result integrity mismatch')
        parent, original = self.runtime._row(row['item_id'])
        artifact = {'domain': RUNTIME_VERSION + '/proposal', 'kind': 'artifact',
                    'sender': self.runtime.identity, 'recipient': original['sender'],
                    'context': original['context'], 'task_id': original['task_id'],
                    'parent_id': row['item_id'], 'title': 'Synthetic research result', 'text': result,
                    'artifact_digest': row['result_digest'], 'created_at': row['claimed_at'],
                    'expires': original['expires']}
        artifact['source_permissions'] = self.runtime._permissions(artifact, None)
        self.runtime._validate_body(artifact, self.runtime.identity,
            self.runtime.exchange.peer_public(parent['peer_id']), sending=True)
        review = {'domain': VERSION + '/result-review', 'run_id': row['id'], 'item_id': row['item_id'],
                  'context': original['context'], 'parent_id': row['item_id'],
                  'recipient': original['sender'], 'source_permissions_digest': digest(original['source_permissions']),
                  'provider_review_digest': row['digest'], 'result_digest': row['result_digest'],
                  'response_id': row['response_id'], 'title': artifact['title'], 'text': result,
                  'expires': artifact['expires'], 'artifact_id': digest(artifact), 'artifact': artifact,
                  'synthetic_only': True, 'scope': 'Stage this exact local draft only; release requires a separate owner review'}
        return review

    def _status(self, session, row):
        result = self.adapter._status(row)
        mapping = self._mapping(row['id'])
        result.update({'artifact_id': mapping['artifact_id'] if mapping else None,
                       'artifact_state': self.runtime._status(self.runtime._row(mapping['artifact_id'])[0])['state'] if mapping else None,
                       'result_review_digest': mapping['review_digest'] if mapping else None,
                       'allowed_actions': [], 'workflow_enabled': self.enabled, 'live_enabled': False})
        actions = []
        if not row['cancelled']:
            actions.append('cancel')
            try:
                self._current_request(session, row)
                if row['state'] == 'prepared':
                    actions.extend(('review', 'approve'))
                elif row['state'] == 'approved' and row['expires'] > self.runtime._now():
                    actions.append('review')
                    if self.runtime.db.execute('SELECT COUNT(*) FROM pilot_provider_runs WHERE claimed_at IS NOT NULL').fetchone()[0] < self.adapter.budget.max_requests:
                        actions.append('run')
                elif row['state'] == 'completed':
                    preview = self._result_review(session, row)
                    result['result_review_digest'] = digest(preview)
                    actions.append('review_result')
                    if mapping is None:
                        actions.append('stage')
            except (ValueError, PermissionError):
                pass  # Metadata history survives withdrawal; content does not.
        result['allowed_actions'] = actions if self.enabled else []
        return result

    def prepare(self, session, item_id):
        self._enabled()
        hash_id(item_id)
        with self.runtime._transaction(session):
            _, body = self.runtime._row(item_id)
            binding = {'item_id': item_id, 'context': body['context'],
                       'payload_digest': body['artifact_digest'], **FIXTURE_GRANT}
            self.runtime.authorise_provider(session, binding)
        # The adapter rechecks the full binding in its own atomic prepare.
        self.adapter.prepare(session, 'work-' + item_id, binding)
        return self.status(session, 'work-' + item_id)

    def status(self, session, run_id):
        with self.runtime._transaction(session):
            return self._status(session, self._run(session, run_id))

    def list_runs(self, session):
        with self.runtime._transaction(session):
            if self.adapter is None:
                return []
            rows = self.runtime.db.execute("SELECT id FROM pilot_provider_runs WHERE id LIKE 'work-%' ORDER BY id").fetchall()
            return [self._status(session, self._run(session, row['id'])) for row in rows]

    def review(self, session, run_id):
        self._enabled()
        with self.runtime._transaction(session):
            self._run(session, run_id)
        value = self.adapter.review(session, run_id)
        return {'run_id': run_id, **value, 'synthetic_only': True}

    def approve(self, session, run_id, review_digest, expires):
        self._enabled()
        with self.runtime._transaction(session):
            self._run(session, run_id)
        self.adapter.approve(session, run_id, review_digest, expires=expires)
        return self.status(session, run_id)

    def dispatch(self, session, run_id, review_digest):
        self._enabled()
        with self.runtime._transaction(session):
            row = self._run(session, run_id)
            if type(review_digest) is not str or row['digest'] != review_digest:
                raise WorkflowDenied('Exact approved provider review required')
        self.adapter.dispatch(session, run_id)
        return self.status(session, run_id)

    def cancel(self, session, run_id):
        self._enabled()
        with self.runtime._transaction(session):
            row = self._run(session, run_id)
            mapping = self._mapping(run_id)
            if row['cancelled']:
                return self._status(session, row)
            self.runtime.db.execute('UPDATE pilot_provider_runs SET cancelled=1,state=? WHERE id=?',
                ('cancelled' if row['claimed_at'] is None else row['state'], run_id))
            if mapping:
                artifact, body = self.runtime._row(mapping['artifact_id'])
                self.runtime._cancel(session, artifact['id'], self.runtime._review(artifact, body)['review_digest'])
            self.runtime._event('workflow_cancelled', row['item_id'], run_id=run_id,
                                artifact_id=mapping['artifact_id'] if mapping else None)
            return self._status(session, self._run(session, run_id))

    def review_result(self, session, run_id):
        self._enabled()
        with self.runtime._transaction(session) as commit_checks:
            review = self._result_review(session, self._run(session, run_id))
            def still_available():
                if digest(self._result_review(session, self._run(session, run_id))) != digest(review):
                    raise WorkflowDenied('Original result review changed before return')
            commit_checks.append(still_available)
            return {'run_id': run_id, 'review_digest': digest(review), 'review': review,
                    'content': review['text'], 'synthetic_only': True, 'authorises_publication': False}

    def stage_result(self, session, run_id, review_digest):
        self._enabled()
        with self.runtime._transaction(session) as commit_checks:
            row = self._run(session, run_id)
            mapping = self._mapping(run_id)
            if mapping:
                if type(review_digest) is not str or mapping['review_digest'] != review_digest:
                    raise WorkflowDenied('Original result review cannot be replaced')
                # Original metadata only: no source text or new proposal after expiry.
                return self._status(session, row)
            review = self._result_review(session, row)
            if type(review_digest) is not str or digest(review) != review_digest:
                raise WorkflowDenied('Exact original result review required')
            def current_at_commit():
                current = self._result_review(session, self._run(session, run_id))
                if digest(current) != review_digest:
                    raise WorkflowDenied('Result staging authority changed before commit')
            commit_checks.append(current_at_commit)
            staged = self.runtime._stage_proposal(review['artifact'])
            if staged['state'] != 'draft' or staged['id'] != review['artifact_id']:
                raise WorkflowDenied('Original result must stage one exact unreleased draft')
            self.runtime.db.execute('INSERT INTO pilot_workflow_artifacts VALUES(?,?,?,?)',
                (run_id, staged['id'], review_digest, self.runtime.storage.seal('pilot_workflow_artifacts', run_id, 'review', canonical(review).decode())))
            self.runtime._event('workflow_result_staged', row['item_id'], run_id=run_id,
                                result_digest=row['result_digest'], artifact_id=staged['id'],
                                review_digest=review_digest)
            return self._status(session, self._run(session, run_id))
