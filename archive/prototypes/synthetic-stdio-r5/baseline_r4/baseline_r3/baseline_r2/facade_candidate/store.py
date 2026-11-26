"""Sequential local composition; no transport, privileged callback, or retry code."""
import json
import sqlite3

from independent_peer.protocol import (Rejected, canonical, descriptor, digest, exact,
    grant_body, hashid, hexid, need, scope, task, token, verify, PROTOCOL, unb64)

SCHEMA = 'offline-exact-text-proposal/1'
MAX_HISTORY = 64


def detached(value):
    return json.loads(canonical(value))


def bounded_text(value):
    need(type(value) is str and bool(value), 'nonempty text required')
    need(len(value) <= 1024, 'text exceeds 1024 scalar bound before encoding')
    try:
        encoded = value.encode('utf-8', errors='strict')
    except UnicodeError as exc:
        raise Rejected('Unicode scalar text required') from exc
    need(len(encoded) <= 1024, 'text exceeds 1024 UTF-8 bytes')
    return value


class ProposalStore:
    """Trusted composition object, never a model tool. One file per fixed actor."""
    def __init__(self, path, *, actor, task_value, public):
        task(task_value)
        exact(public, 'alice bob')
        for name, value in public.items():
            descriptor(value)
            need(value['actor'] == name, 'descriptor actor mismatch')
        need(actor in ('alice', 'bob'), 'actor')
        binding = detached({'schema': SCHEMA, 'actor': actor, 'task': task_value,
                            'public': public})
        self._binding = binding
        self._db = sqlite3.connect(path)
        try:
            self._db.execute('PRAGMA synchronous=FULL')
            with self._db:
                self._db.execute('CREATE TABLE IF NOT EXISTS binding (singleton INTEGER PRIMARY KEY CHECK(singleton=1), value TEXT NOT NULL)')
                self._db.execute('CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, value TEXT NOT NULL)')
                self._db.execute('CREATE TABLE IF NOT EXISTS publication (singleton INTEGER PRIMARY KEY CHECK(singleton=1), value TEXT NOT NULL)')
                row = self._db.execute('SELECT value FROM binding WHERE singleton=1').fetchone()
                if row is None:
                    self._db.execute('INSERT INTO binding VALUES (1,?)', (canonical(binding).decode(),))
                else:
                    need(json.loads(row[0]) == binding, 'store binding is immutable')
        except BaseException:
            self._db.close()
            raise

    def close(self):
        self._db.close()

    def _get(self, proposal_id):
        hashid(proposal_id)
        row = self._db.execute('SELECT value FROM proposals WHERE id=?', (proposal_id,)).fetchone()
        need(row is not None, 'unknown local proposal')
        return json.loads(row[0])

    def _save(self, record):
        self._db.execute('INSERT OR REPLACE INTO proposals VALUES (?,?)',
                         (record['proposal_id'], canonical(record).decode()))

    def _view(self, record):
        # Exact allowlist: no grant, packet, owner command, private/raw peer lane.
        return detached({key: record[key] for key in (
            'proposal_id', 'content_digest', 'state', 'operation_id', 'command_digest',
            'message_id', 'message_digest', 'packet_digest', 'evidence_basis')})


class AssistantFacade:
    """Dispatch ONLY these three methods. Python object access remains trusted."""
    def __init__(self, store):
        self._store = store

    def propose(self, arguments):
        exact(arguments, 'text')
        text = bounded_text(arguments['text'])
        meaning = {'binding': self._store._binding, 'text': text}
        proposal_id = digest(meaning)
        with self._store._db:
            row = self._store._db.execute('SELECT value FROM proposals WHERE id=?', (proposal_id,)).fetchone()
            if row is not None:
                return self._store._view(json.loads(row[0]))
            count = self._store._db.execute('SELECT count(*) FROM proposals').fetchone()[0]
            need(count < MAX_HISTORY, 'finite proposal history full; no eviction or reset')
            record = dict(proposal_id=proposal_id, content_digest=digest({'text': text}),
                          text=text, state='pending', operation_id=None, command_digest=None,
                          message_id=None, message_digest=None, packet_digest=None,
                          evidence_basis='local unsigned proposal')
            self._store._save(record)
        return self._store._view(record)

    def status(self, arguments):
        exact(arguments, 'proposal_id')
        return self._store._view(self._store._get(arguments['proposal_id']))

    def processed_inbox(self, arguments):
        exact(arguments, '')
        row = self._store._db.execute('SELECT value FROM publication WHERE singleton=1').fetchone()
        if row is None:
            return {'knowledge': 'No trusted local snapshot published.', 'publication': 0, 'items': []}
        return json.loads(row[0])


class OwnerReview:
    """Privileged local API. Calling it is not human authentication or a model tool."""
    def __init__(self, store):
        self._store = store

    def review(self, proposal_id, *, grant=None):
        record = self._store._get(proposal_id)
        return {'binding': detached(self._store._binding), 'text': record['text'],
                'status': self._store._view(record),
                'selected_grant': detached(grant), 'selected_grant_digest': digest(grant) if grant is not None else None,
                'action': 'Explicit approval AND release; not delivery or processing.'}

    def decline(self, proposal_id):
        with self._store._db:
            record = self._store._get(proposal_id)
            need(record['state'] == 'pending', 'only pending proposals can be declined')
            record['state'] = 'declined'
            record['evidence_basis'] = 'local owner declined exact meaning'
            self._store._save(record)
        return self._store._view(record)

    def prepare_approve_and_release(self, proposal_id, *, reviewed_content_digest, reviewed_grant_digest, grant):
        """Explicit owner decision; return command for separate MANUAL execution once.

        Commits unknown before returning any command. Never returns a second command
        for this proposal, even if the first was not executed or was rejected.
        """
        binding = self._store._binding
        actor = binding['actor']
        peer = 'bob' if actor == 'alice' else 'alice'
        grant = detached(grant)
        need(reviewed_grant_digest == digest(grant), 'review exact selected grant first')
        body = verify(grant, 'grant', binding['public'][peer])
        grant_body(body, scope(binding['task'], actor, peer,
                   'request' if actor == 'alice' else 'result'), binding['public'])
        with self._store._db:
            record = self._store._get(proposal_id)
            need(record['state'] == 'pending', 'proposal is not pending; no retry/reset')
            need(reviewed_content_digest == record['content_digest'], 'review exact content first')
            command = {'op': 'approve_send', 'operation_id': token(), 'payload': record['text'], 'grant': grant}
            record.update(state='unknown', operation_id=command['operation_id'],
                          command_digest=digest(command), evidence_basis='command prepared; execution/release outcome unknown')
            self._store._save(record)
        return detached(command)

    def record_response(self, proposal_id, *, operation_id, command_digest, response):
        """Caller attests this is the actual response to that exact issued command.

        Not a peer-evidence verifier. Only fixed owner composition may call this.
        Invalid/unavailable responses leave durable unknown untouched.
        """
        response = detached(response)
        exact(response, 'id message_digest packet release historical_replay')
        hexid(response['id']); hashid(response['message_digest'])
        need(response['release'] == 'approved_and_released' and response['historical_replay'] is False,
             'expected first actual approval/release response')
        _released_packet(self._store, response['packet'])
        with self._store._db:
            record = self._issued(proposal_id, operation_id, command_digest)
            record.update(state='released', message_id=response['id'], message_digest=response['message_digest'],
                          packet_digest=digest(response['packet']), evidence_basis='trusted caller recorded actual endpoint release response; delivery unknown')
            self._store._save(record)
        return self._store._view(record)

    def record_rejection(self, proposal_id, *, operation_id, command_digest, rejection):
        """Only an actual endpoint Rejected response, NOT timeout/exception/silence.

        Caller must know it belongs to the exact issued operation. Generic Python
        exceptions cannot establish rejection. Rejection never enables resubmission.
        """
        need(type(rejection) is Rejected, 'known endpoint rejection required')
        with self._store._db:
            record = self._issued(proposal_id, operation_id, command_digest)
            record.update(state='rejected', evidence_basis='trusted caller recorded actual endpoint rejection')
            self._store._save(record)
        return self._store._view(record)

    def _issued(self, proposal_id, operation_id, command_digest):
        record = self._store._get(proposal_id)
        need(record['state'] == 'unknown', 'outcome is already final or command not issued')
        need(record['operation_id'] == operation_id and record['command_digest'] == command_digest,
             'operation correlation mismatch')
        return record

    def reconcile_snapshot(self, proposal_id, snapshot):
        """Fixed local snapshot can establish exact committed outgoing content only.

        Absence is inconclusive. No packet returned, no command retried, no delivery
        inferred. Only one outgoing slot exists in r1. This is NOT proof that the
        prepared operation caused it; evidence basis explicitly says content match.
        """
        snapshot = _local_snapshot(self._store, snapshot)
        with self._store._db:
            record = self._store._get(proposal_id)
            need(record['state'] == 'unknown', 'only unknown requires reconciliation')
            matches = [v for v in snapshot['outgoing'] if v['payload'] == record['text']]
            if matches:
                need(len(matches) == 1, 'ambiguous outgoing content')
                view = matches[0]
                _projection_item(view, 'request' if self._store._binding['actor'] == 'alice' else 'result', processed=False)
                record.update(state='committed_content_observed', message_id=view['id'],
                    message_digest=view['message_digest'], evidence_basis='fixed local snapshot exact outgoing content match; operation causation and release/delivery unknown')
                self._store._save(record)
        return self._store._view(record)


def _released_packet(store, packet):
    """Validate public wire shape/bindings only, not encrypted message contents."""
    exact(packet, 'header ciphertext')
    header = packet['header']
    exact(header, 'protocol sender recipient sender_binding recipient_binding ephemeral nonce')
    binding = store._binding
    actor = binding['actor']
    peer = 'bob' if actor == 'alice' else 'alice'
    need(header['protocol'] == PROTOCOL and header['sender'] == actor and header['recipient'] == peer,
         'release packet direction/protocol mismatch')
    need(header['sender_binding'] == digest(binding['public'][actor]) and
         header['recipient_binding'] == digest(binding['public'][peer]), 'release packet binding mismatch')
    unb64(header['ephemeral'], 32)
    unb64(header['nonce'], 12)
    # Existing protocol encoding bound plus the minimum AES-GCM authentication tag.
    need(len(unb64(packet['ciphertext'])) >= 16, 'release ciphertext too short')


def _local_snapshot(store, snapshot):
    snapshot = detached(snapshot)
    exact(snapshot, 'actor pid identity configured policy incoming outgoing processed_projection owner_operation_count')
    binding = store._binding
    need(snapshot['actor'] == binding['actor'] and snapshot['identity'] == binding['public'][binding['actor']]
         and snapshot['configured'] is True, 'snapshot actor/incarnation mismatch')
    need(type(snapshot['outgoing']) is list and type(snapshot['processed_projection']) is list,
         'snapshot lists required')
    return snapshot


def _projection_item(item, kind, *, processed=True):
    exact(item, 'id kind message_digest received_evidence_present processed_evidence_present payload')
    hexid(item['id']); hashid(item['message_digest']); bounded_text(item['payload'])
    need(item['kind'] == kind, 'projection kind')
    need(type(item['received_evidence_present']) is bool and type(item['processed_evidence_present']) is bool,
         'evidence flags')
    if processed:
        need(item['processed_evidence_present'] is True, 'processed projection required')
    return {key: item[key] for key in ('id', 'kind', 'message_digest', 'payload')}


class SnapshotPublisher:
    """Trusted caller supplies actual fixed local inspect response; no callback."""
    def __init__(self, store):
        self._store = store

    def publish(self, snapshot):
        snapshot = _local_snapshot(self._store, snapshot)
        kind = 'result' if self._store._binding['actor'] == 'alice' else 'request'
        need(len(snapshot['processed_projection']) <= 1, 'r1 fixed incoming slot')
        items = [_projection_item(item, kind) for item in snapshot['processed_projection']]
        with self._store._db:
            row = self._store._db.execute('SELECT value FROM publication WHERE singleton=1').fetchone()
            old = json.loads(row[0]) if row else {'publication': 0, 'items': []}
            # Processed historical knowledge must not disappear on cancel or stale publication.
            need(not old['items'] or old['items'] == items, 'cannot replace/erase published history')
            value = {'knowledge': 'Last trusted-published local knowledge; not fresh network truth or proof of human/model work.',
                     'publication': old['publication'] + 1, 'items': items}
            self._store._db.execute('INSERT OR REPLACE INTO publication VALUES (1,?)', (canonical(value).decode(),))
        return detached(value)
