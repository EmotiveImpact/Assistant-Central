"""Trusted-console owner inbox. Public data only; no signing, identity enrollment or I/O.

A local owner selector is not authentication. The dedicated workflow executor must
not expose legacy raw approval APIs. Request approval, durable execution and remote
receipt are distinct. Generated private keys never enter this module.
"""
import json
import re
import secrets
from datetime import datetime, timezone
from network import Denied, canonical, digest, snapshot_envelope
from owner_auth import DOMAIN, validate_decision
from bound_identity import DELIVERY_DOMAIN, verify_owner
from owner_withdrawal import DOMAIN as WITHDRAWAL_DOMAIN, validate_withdrawal, verify_withdrawal
from review import render_review, person


class OwnerWorkflow:
    def __init__(self, gateway, outbox):
        if gateway is not outbox.gateway:
            raise Denied('Owner workflow requires the exact outbox gateway')
        self.gateway, self.box = gateway, outbox
        self.store, self.db, self.session, self.registry = gateway.delivery, gateway.db, gateway.session, outbox.registry
        self.db.execute('''CREATE TABLE IF NOT EXISTS owner_requests (
            nonce TEXT PRIMARY KEY, context TEXT NOT NULL, owner TEXT NOT NULL,
            decision TEXT NOT NULL, envelope TEXT NOT NULL, meaning TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('pending','deferred','declined','authorized','submitted')),
            revision INTEGER NOT NULL DEFAULT 0, signed TEXT, result TEXT)''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS owner_request_replacements (
            original TEXT PRIMARY KEY, replacement TEXT NOT NULL UNIQUE,
            context TEXT NOT NULL, owner TEXT NOT NULL, review_digest TEXT NOT NULL,
            created_at INTEGER NOT NULL, CHECK(original != replacement))''')
        self.db.execute('''CREATE TABLE IF NOT EXISTS owner_pairing_reviews (
            source TEXT NOT NULL, review_digest TEXT NOT NULL, direction_owner TEXT NOT NULL,
            pairing TEXT NOT NULL, context TEXT NOT NULL, created_at INTEGER NOT NULL,
            PRIMARY KEY(source,review_digest,direction_owner), CHECK(source != pairing))''')

        self.db.execute("""CREATE TABLE IF NOT EXISTS owner_withdrawal_successors (
            original TEXT PRIMARY KEY, successor TEXT NOT NULL UNIQUE,
            context TEXT NOT NULL, owner TEXT NOT NULL, review_digest TEXT NOT NULL,
            created_at INTEGER NOT NULL, CHECK(original != successor))""")

    def _withdrawal(self, nonce):
        return self.db.execute('SELECT * FROM owner_authorization_withdrawals WHERE source_nonce=?',(nonce,)).fetchone()

    def _unused_authorization(self, row):
        if row['state']!='authorized' or row['signed'] is None:
            raise Denied('Withdrawal requires an authorized, unsubmitted request')
        decision, message = self._validate(json.loads(row['decision']),json.loads(row['envelope']))
        signed=json.loads(row['signed'])
        if type(signed) is not dict or set(signed)!={'decision','signature'} or signed['decision']!=decision:
            raise Denied('Stored authorization disagrees with the original request')
        if decision['nonce']!=row['nonce'] or decision['owner']!=row['owner'] or decision['context']!=row['context']:
            raise Denied('Original authorization scope does not match')
        if decision['action']=='send': self.registry.verify_delivery(signed,message)
        else: verify_owner(self.registry.owner_roots[row['owner']],DOMAIN,decision,signed['signature'])
        for table,field in (('owner_decisions','nonce'),('encrypted_outbox','nonce'),('approvals','id'),('deliveries','id'),('transitions','delivery_id')):
            if self.db.execute(f'SELECT 1 FROM {table} WHERE {field}=?',(row['nonce'],)).fetchone():
                raise Denied('Execution evidence exists; authorization is not provably unused')
        return decision,message,digest({'decision':decision,'envelope':message})

    def prepare_withdrawal(self, owner, nonce, review_digest):
        """Return an unsigned withdrawal challenge. Never execute or discard evidence."""
        with self.store.transaction():
            row=self._row(owner,nonce); prior=self._withdrawal(nonce)
            if prior:
                if type(review_digest) is not str or prior['review_digest']!=review_digest:
                    raise Denied('Original withdrawal review token does not match')
                return {'already_withdrawn':True,'card':self._card(row)}
            decision,message,fingerprint=self._unused_authorization(row)
            if type(review_digest) is not str or digest(self._snapshot(row))!=review_digest:
                raise Denied('Review changed; inspect authorization again before withdrawing')
            now=int(self.store.clock())
            body={'version':1,'domain':WITHDRAWAL_DOMAIN,'owner':owner,'context':self.session.context,
                  'nonce':secrets.token_hex(16),'issued_at':now,'expires_at':now+300,
                  'target':{'request_id':nonce,'fingerprint':fingerprint,'review_digest':review_digest}}
            return {'withdrawal':validate_withdrawal(body),'original':{'decision':decision,'envelope':message}}

    def withdraw(self, signed):
        """Atomically fence one unused authorization with a fresh owner signature."""
        if type(signed) is not dict or set(signed)!={'withdrawal','signature'}:
            raise Denied('Exact signed withdrawal required')
        body=validate_withdrawal(signed['withdrawal']);self._owner(body['owner'])
        body=verify_withdrawal(self.registry.owner_roots[body['owner']],signed)
        if body['context']!=self.session.context: raise Denied('Withdrawal context is not enrolled')
        target=body['target'];nonce=target['request_id']
        with self.store.transaction():
            row=self._row(body['owner'],nonce);prior=self._withdrawal(nonce)
            if prior:
                if prior['token']!=canonical(body) or prior['signature']!=signed['signature']:
                    raise Denied('Authorization already withdrawn with a different token')
                return self._card(row)
            if not body['issued_at']<=self.store.clock()<body['expires_at']:
                raise Denied('Withdrawal expired or not yet valid')
            _,_,fingerprint=self._unused_authorization(row)
            if fingerprint!=target['fingerprint'] or digest(self._snapshot(row))!=target['review_digest']:
                raise Denied('Withdrawal does not match exact authorization and current review')
            if self.db.execute('SELECT COUNT(*) FROM owner_authorization_withdrawals').fetchone()[0]>=self.store.max_records:
                raise Denied('Withdrawal record limit reached; no implicit deletion')
            if self.db.execute('SELECT 1 FROM owner_authorization_withdrawals WHERE withdrawal_nonce=?',(body['nonce'],)).fetchone():
                raise Denied('Withdrawal nonce already used')
            self.db.execute('INSERT INTO owner_authorization_withdrawals VALUES (?,?,?,?,?,?,?,?,?)',
                            (nonce,body['owner'],body['context'],fingerprint,target['review_digest'],body['nonce'],canonical(body),signed['signature'],int(self.store.clock())))
            self.db.execute('UPDATE owner_requests SET revision=revision+1 WHERE nonce=?',(nonce,))
            return self._card(self._row(body['owner'],nonce))

    def prepare_after_withdrawal(self, owner, nonce, review_digest):
        """A separate explicit unsigned successor, requiring fresh permissions/approval."""
        with self.store.transaction():
            row=self._row(owner,nonce)
            link=self.db.execute('SELECT * FROM owner_withdrawal_successors WHERE original=?',(nonce,)).fetchone()
            if link:
                if type(review_digest) is not str or link['review_digest']!=review_digest:
                    raise Denied('Original fresh-review token does not match')
                return self._card(self._row(owner,link['successor']))
            if not self._withdrawal(nonce): raise Denied('Authorization must first be withdrawn')
            if type(review_digest) is not str or digest(self._snapshot(row))!=review_digest:
                raise Denied('Review changed; inspect withdrawal before preparing a fresh review')
            self._unused_authorization(row)
            if self.db.execute('SELECT COUNT(*) FROM owner_withdrawal_successors').fetchone()[0]>=self.store.max_records:
                raise Denied('Withdrawal successor record limit reached')
            decision,message,meaning=self._replacement_draft(row)
            self._insert_draft(decision,message,meaning)
            self.db.execute('INSERT INTO owner_withdrawal_successors VALUES (?,?,?,?,?,?)',
                            (nonce,decision['nonce'],self.session.context,owner,review_digest,int(self.store.clock())))
            self.db.execute('UPDATE owner_requests SET revision=revision+1 WHERE nonce=?',(nonce,))
            return self._card(self._row(owner,decision['nonce']))

    def _owner(self, owner):
        if type(owner) is not str or owner not in self.registry.owner_roots:
            raise Denied('Unknown local fixture owner')

    def _row(self, owner, nonce):
        self._owner(owner)
        if type(nonce) is not str or not re.fullmatch('[a-f0-9]{32}', nonce):
            raise Denied('Invalid owner request ID')
        row = self.db.execute('SELECT * FROM owner_requests WHERE nonce=? AND context=? AND owner=?',
                              (nonce, self.session.context, owner)).fetchone()
        if row is None: raise Denied('No request for this owner')
        return row

    def _validate(self, decision, envelope):
        if type(decision) is dict and decision.get('domain') == DELIVERY_DOMAIN:
            decision, message = self.registry.validate_delivery(decision, envelope)
            if message is None: raise Denied('Send request requires its exact message')
        else:
            decision = validate_decision(decision)
            if decision['action'] == 'send' or envelope is not None:
                raise Denied('Only identity-bound send drafts may contain messages')
            message = None
        if decision['owner'] not in self.registry.owner_roots or decision['context'] != self.session.context:
            raise Denied('Request owner/context is not enrolled')
        return decision, message

    def _current(self, decision, message):
        now = int(self.store.clock())
        if not decision['issued_at'] <= now < decision['expires_at']:
            raise Denied('Request expired or is not yet valid; prepare a new review')
        action, target, owner = decision['action'], decision['target'], decision['owner']
        if action == 'send':
            self.box._current_permission(decision)
            self.registry.permits(owner, target['recipient'], now)
            self.session._restore()._validate(message)
            if self.db.execute("SELECT 1 FROM encrypted_outbox WHERE context=? AND sender=? AND recipient=? AND message_type=? AND state!='blocked'",
                               (self.session.context, owner, target['recipient'], message['type'])).fetchone():
                raise Denied('This scheduling step already has a pending or completed delivery')
        elif action in ('pair', 'revoke'):
            if target['peer'] not in self.registry.owner_roots:
                raise Denied('Peer is not enrolled')
            if target['contact_version'] != self.store.contact_version(owner, target['peer'], self.session.context):
                raise Denied('Contact changed; prepare a new review')
            if action == 'pair': self.store._require_active(self.session.context)
        elif target['meeting'] != self.session.meeting.id:
            raise Denied('Cancellation names another meeting')

    def _draft(self, owner, action, *, peer=None, envelope=None, ttl=300, pair_ttl=3600, nonce=None):
        """Construct and validate an unsigned draft. A caller supplies the transaction."""
        self._owner(owner)
        if type(action) is not str or action not in ('send','pair','revoke','cancel'):
            raise Denied('Unsupported owner request')
        if type(ttl) is not int or not 1 <= ttl <= 600:
            raise Denied('Request expiry must be within ten minutes')
        if action == 'send':
            message = snapshot_envelope(envelope)
            if peer is not None or message['sender'] != owner:
                raise Denied('Send request owner does not match exact sender')
            target = {'recipient':message['recipient'], 'envelope_digest':digest(message),
                      'pair_versions':self.gateway.contact_versions(owner,message['recipient']),
                      'sender_binding':self.registry.binding_digest(owner),
                      'recipient_binding':self.registry.binding_digest(message['recipient'])}
        else:
            if envelope is not None: raise Denied('Control request cannot contain a message')
            message = None
            if action == 'cancel':
                if peer is not None: raise Denied('Cancellation cannot target a peer')
                target = {'meeting':self.session.meeting.id}
            else:
                self._owner(peer)
                target = {'peer':peer,'contact_version':self.store.contact_version(owner,peer,self.session.context)}
                if action == 'pair': target['ttl'] = pair_ttl
        now = int(self.store.clock())
        decision = {'version':1,'domain':DELIVERY_DOMAIN if action=='send' else DOMAIN,
                    'action':action,'owner':owner,'context':self.session.context,
                    'nonce':nonce if nonce is not None else secrets.token_hex(16),
                    'issued_at':now,'expires_at':now+ttl,'target':target}
        decision, message = self._validate(decision, message)
        self._current(decision, message)
        meaning = digest({'owner':owner,'action':action,'target':target,'envelope':message})
        return decision, message, meaning

    def _insert_draft(self, decision, message, meaning):
        if not self.db.in_transaction: raise Denied('Draft insertion needs an active transaction')
        if self.db.execute('SELECT COUNT(*) FROM owner_requests').fetchone()[0] >= self.store.max_records:
            raise Denied('Owner request record limit reached; no implicit deletion')
        self.db.execute('''INSERT INTO owner_requests (nonce,context,owner,decision,envelope,meaning,state)
                           VALUES (?,?,?,?,?,?,'pending')''',
                        (decision['nonce'],self.session.context,decision['owner'],canonical(decision),canonical(message),meaning))

    def prepare(self, owner, action, *, peer=None, envelope=None, ttl=300, pair_ttl=3600):
        with self.store.transaction():
            decision, message, meaning = self._draft(owner,action,peer=peer,envelope=envelope,ttl=ttl,pair_ttl=pair_ttl)
            now = int(self.store.clock())
            for row in self.db.execute("SELECT * FROM owner_requests r WHERE context=? AND meaning=? AND state IN ('pending','deferred') AND NOT EXISTS (SELECT 1 FROM owner_request_replacements l WHERE l.original=r.nonce) AND NOT EXISTS (SELECT 1 FROM owner_authorization_withdrawals w WHERE w.source_nonce=r.nonce) ORDER BY rowid DESC", (self.session.context,meaning)):
                prior = json.loads(row['decision'])
                if prior['issued_at'] <= now < prior['expires_at']:
                    return self._card(row)
            self._insert_draft(decision,message,meaning)
            return self._card(self._row(owner,decision['nonce']))

    def _replacement_draft(self, row, *, preview=False):
        decision, message = self._validate(json.loads(row['decision']),json.loads(row['envelope']))
        return self._draft(row['owner'],decision['action'],peer=decision['target'].get('peer'),
                           envelope=message,ttl=decision['expires_at']-decision['issued_at'],
                           pair_ttl=decision['target'].get('ttl',3600),nonce=row['nonce'] if preview else None)

    def replace_review(self, owner, nonce, review_digest):
        """Explicitly prepare a fresh unsigned review. Never renew approval/identity.

        The original is retained. Exact retries return the same replacement; no
        declined, authorized, submitted or uncertain operation can be replaced.
        """
        with self.store.transaction():
            row = self._row(owner,nonce)
            link = self.db.execute('SELECT * FROM owner_request_replacements WHERE original=?',(nonce,)).fetchone()
            if link:
                if (type(review_digest) is not str or link['review_digest']!=review_digest
                        or link['owner']!=owner or link['context']!=self.session.context):
                    raise Denied('Original replacement review does not match; inspect its recorded successor')
                return self._card(self._row(owner,link['replacement']))
            card = self._card(row)
            if type(review_digest) is not str or card['review_digest']!=review_digest:
                raise Denied('Review changed; inspect it again before requesting a replacement')
            if row['state'] not in ('pending','deferred') or card['state'] not in ('expired','stale') or row['signed'] is not None:
                raise Denied('Only expired or stale unsigned pending reviews may be replaced')
            for table, field in (('owner_decisions','nonce'),('encrypted_outbox','nonce')):
                if self.db.execute(f'SELECT 1 FROM {table} WHERE {field}=?',(nonce,)).fetchone():
                    raise Denied('A committed or uncertain operation cannot become a replacement review')
            if self.db.execute('SELECT COUNT(*) FROM owner_request_replacements').fetchone()[0] >= self.store.max_records:
                raise Denied('Review replacement record limit reached; no implicit deletion')
            decision, message, meaning = self._replacement_draft(row)
            self._insert_draft(decision,message,meaning)
            self.db.execute('INSERT INTO owner_request_replacements VALUES (?,?,?,?,?,?)',
                            (nonce,decision['nonce'],self.session.context,owner,review_digest,int(self.store.clock())))
            self.db.execute('UPDATE owner_requests SET revision=revision+1 WHERE nonce=?',(nonce,))
            return self._card(self._row(owner,decision['nonce']))

    def _snapshot(self, row):
        # Conservative stale-review guard: any session transition, contact change,
        # cancellation or outbox state change requires the owner to review again.
        def rows(query): return [dict(r) for r in self.db.execute(query,(self.session.context,))]
        linkage = self.db.execute('SELECT * FROM owner_request_replacements WHERE original=?',(row['nonce'],)).fetchone()
        return {'registry':self.registry.fingerprint,'request':dict(row),'replacement':dict(linkage) if linkage else None,
                'withdrawal':dict(self._withdrawal(row['nonce'])) if self._withdrawal(row['nonce']) else None,
                'withdrawal_successor':[dict(r) for r in self.db.execute('SELECT * FROM owner_withdrawal_successors WHERE original=?',(row['nonce'],))],
                'contacts':rows('SELECT * FROM contacts WHERE purpose=? ORDER BY owner,peer'),
                'versions':rows('SELECT * FROM contact_versions WHERE purpose=? ORDER BY owner,peer'),
                'cancel':rows('SELECT * FROM cancellations WHERE purpose=?'),
                'deliveries':rows('SELECT nonce,state,attempts FROM encrypted_outbox WHERE context=? ORDER BY nonce'),
                'transitions':[dict(r) for r in self.db.execute('SELECT seq,delivery_id FROM transitions WHERE session_id=? ORDER BY seq',(self.session.meeting.id,))]}

    def _pairing_recovery(self, row):
        """Read-only eligibility, independent of the expired original signature window."""
        decision, message = self._validate(json.loads(row['decision']),json.loads(row['envelope']))
        if decision['action']!='send' or row['state'] not in ('pending','deferred') or row['signed'] is not None:
            raise Denied('Pairing review recovery needs an unsigned pending send')
        if self.db.execute('SELECT 1 FROM owner_request_replacements WHERE original=?',(row['nonce'],)).fetchone():
            raise Denied('Superseded send cannot request pairing recovery')
        for table in ('owner_decisions','encrypted_outbox'):
            if self.db.execute(f'SELECT 1 FROM {table} WHERE nonce=?',(row['nonce'],)).fetchone():
                raise Denied('Committed or uncertain send cannot request pairing recovery')
        self.store._require_active(self.session.context)
        sender, recipient = decision['owner'], decision['target']['recipient']
        self.registry.permits(sender,recipient,int(self.store.clock()))
        self.session._restore()._validate(message)
        if self.db.execute("SELECT 1 FROM encrypted_outbox WHERE context=? AND sender=? AND recipient=? AND message_type=? AND state!='blocked'",
                           (self.session.context,sender,recipient,message['type'])).fetchone():
            raise Denied('This scheduling step already has a pending or completed delivery')
        missing=[]
        for owner,peer in dict.fromkeys(((sender,recipient),(recipient,sender))):
            contact=self.db.execute('SELECT expires FROM contacts WHERE owner=? AND peer=? AND purpose=?',
                                    (owner,peer,self.session.context)).fetchone()
            if contact is None or contact['expires']<=self.store.clock():
                missing.append({'owner':owner,'peer':peer,'state':'missing' if contact is None else 'expired',
                                'expires_at':contact['expires'] if contact else None})
        return missing

    def recover_pairing(self, owner, nonce, review_digest, direction_owner):
        """Open one separate unsigned pairing review; never restore either grant.

        The exact source token is idempotent, including after a refusal or later
        replacement. Existing unresolved directional reviews are surfaced rather
        than recreated. Fresh approval and submission by that owner are required.
        """
        with self.store.transaction():
            row=self._row(owner,nonce);self._owner(direction_owner)
            if type(review_digest) is not str or not re.fullmatch('[a-f0-9]{64}',review_digest):
                raise Denied('Invalid source review token')
            link=self.db.execute('SELECT pairing FROM owner_pairing_reviews WHERE source=? AND review_digest=? AND direction_owner=? AND context=?',
                                 (nonce,review_digest,direction_owner,self.session.context)).fetchone()
            if link:return self._card(self._row(direction_owner,link['pairing']))
            if digest(self._snapshot(row))!=review_digest:
                raise Denied('Review changed; inspect the source send again')
            missing=self._pairing_recovery(row)
            direction=next((item for item in missing if item['owner']==direction_owner),None)
            if direction is None:raise Denied('Only a missing direction of this exact send may be reviewed')
            if self.db.execute('SELECT COUNT(*) FROM owner_pairing_reviews').fetchone()[0]>=self.store.max_records:
                raise Denied('Pairing review record limit reached; no implicit deletion')
            existing=None
            for candidate in self.db.execute("SELECT * FROM owner_requests r WHERE context=? AND owner=? AND state!='submitted' AND NOT EXISTS (SELECT 1 FROM owner_request_replacements l WHERE l.original=r.nonce) AND NOT EXISTS (SELECT 1 FROM owner_authorization_withdrawals w WHERE w.source_nonce=r.nonce) ORDER BY rowid DESC",(self.session.context,direction_owner)):
                prior=json.loads(candidate['decision'])
                if prior['action']=='pair' and prior['target']['peer']==direction['peer']:
                    # Submitted grants do not hide older unresolved/refused
                    # reviews. Only explicit replacement supersedes history.
                    existing=candidate
                    break
            if existing is None:
                decision,message,meaning=self._draft(direction_owner,'pair',peer=direction['peer'])
                self._insert_draft(decision,message,meaning)
                pairing=decision['nonce']
            else:pairing=existing['nonce']
            self.db.execute('INSERT INTO owner_pairing_reviews VALUES (?,?,?,?,?,?)',
                            (nonce,review_digest,direction_owner,pairing,self.session.context,int(self.store.clock())))
            self.db.execute('UPDATE owner_requests SET revision=revision+1 WHERE nonce=?',(nonce,))
            return self._card(self._row(direction_owner,pairing))

    def _card(self, row):
        decision, message = self._validate(json.loads(row['decision']),json.loads(row['envelope']))
        link = self.db.execute('SELECT replacement FROM owner_request_replacements WHERE original=?',(row['nonce'],)).fetchone()
        predecessor = self.db.execute('SELECT original FROM owner_request_replacements WHERE replacement=?',(row['nonce'],)).fetchone()
        withdrawal=self._withdrawal(row['nonce'])
        successor=self.db.execute('SELECT successor FROM owner_withdrawal_successors WHERE original=?',(row['nonce'],)).fetchone()
        state, reason = row['state'], None
        if link:
            state, reason = 'superseded', 'This unsigned review was explicitly replaced; it can no longer be approved.'
        if withdrawal:
            state, reason = 'withdrawn', 'Unused authorization permanently withdrawn. Original signed evidence is retained.'
        if not link and not withdrawal and state in ('pending','deferred','authorized'):
            try: self._current(decision,message)
            except Denied as exc:
                state = 'expired' if not decision['issued_at'] <= self.store.clock() < decision['expires_at'] else 'stale'
                reason = str(exc)
        can_replace, replacement_blocker = False, None
        if not link and row['state'] in ('pending','deferred') and state in ('expired','stale'):
            try:
                self._replacement_draft(row,preview=True)
                can_replace = True
            except Denied as exc: replacement_blocker = str(exc)
        can_withdraw, withdrawal_blocker, can_prepare_fresh, fresh_review_blocker = False, None, False, None
        if row['state']=='authorized':
            try:
                self._unused_authorization(row)
                can_withdraw = not bool(withdrawal)
                if withdrawal and not successor:
                    self._replacement_draft(row,preview=True)
                    can_prepare_fresh=True
            except Denied as exc:
                if withdrawal: fresh_review_blocker=str(exc)
                else: withdrawal_blocker=str(exc)
        pairing_reviews=[]
        if not link and decision['action']=='send' and row['state'] in ('pending','deferred') and row['signed'] is None:
            try:pairing_reviews=self._pairing_recovery(row)
            except Denied:pass  # The exact existing stale/replacement blocker is shown above.
        pairing_sources=[dict(r) for r in self.db.execute('''WITH RECURSIVE ancestors(nonce) AS (
            SELECT ? UNION SELECT l.original FROM owner_request_replacements l JOIN ancestors a ON l.replacement=a.nonce)
            SELECT DISTINCT s.owner,s.nonce AS request_id FROM owner_pairing_reviews l
            JOIN owner_requests s ON s.nonce=l.source WHERE l.pairing IN (SELECT nonce FROM ancestors)
            AND l.context=? ORDER BY s.rowid DESC LIMIT 20''',(row['nonce'],self.session.context))]
        action = decision['action']
        review = self._review_text(decision, message)
        return {'request_id':row['nonce'],'owner':row['owner'],'action':action,'state':state,
                'stored_state':row['state'],'revision':row['revision'],'review_digest':digest(self._snapshot(row)),
                'decision':decision,'envelope':message,'review':review,'reason':reason,
                'replaced_by':link['replacement'] if link else None,'replaces':predecessor['original'] if predecessor else None,
                'can_withdraw':can_withdraw,'withdrawal_blocker':withdrawal_blocker,
                'withdrawal':{'nonce':withdrawal['withdrawal_nonce'],'created_at':withdrawal['created_at'],'fingerprint':withdrawal['fingerprint']} if withdrawal else None,
                'can_prepare_fresh':can_prepare_fresh,'fresh_review_blocker':fresh_review_blocker,
                'fresh_review_id':successor['successor'] if successor else None,
                'withdrawn_successor':successor['successor'] if successor else None,
                'withdrawn_source':next((r['original'] for r in self.db.execute('SELECT original FROM owner_withdrawal_successors WHERE successor=?',(row['nonce'],))),None),
                'can_replace':can_replace,'replacement_blocker':replacement_blocker,
                'pairing_reviews':pairing_reviews,'pairing_sources':pairing_sources}

    def _review_text(self, decision, message):
        target, action = decision['target'], decision['action']
        if action == 'send':
            review = render_review(self.session.meeting,message)
            review += '\nRecipient transport binding: '+target['recipient_binding']
            review += '\nExact structured message: '+canonical(message)
        elif action == 'pair':
            review = f"Allow {person(decision['owner'])} to pair with {person(target['peer'])} for this meeting for {target['ttl']} seconds.\nBoth owners must pair. This permits no message or calendar disclosure."
        elif action == 'revoke':
            review = f"Revoke {person(decision['owner'])}'s pairing with {person(target['peer'])} for this meeting.\nUnused approvals become invalid. Re-pairing cannot restore them. Already-started dispatches and disclosed data cannot be recalled."
        else:
            review = 'Cancel this local meeting permanently for all four participants.\nNo new deliveries or scheduling steps may start afterward. An in-flight dispatch may still arrive. No remote notification is sent and no calendar event is cancelled.'
        expires = datetime.fromtimestamp(decision['expires_at'],timezone.utc).isoformat()
        review += f"\nExact meeting: {self.session.meeting.id}\nContext: {self.session.context}\nDecision expires: {expires}\nFictional owner/transport identity only; this is not real-person authentication."
        return review

    def review(self, owner, nonce):
        with self.store.transaction(): return self._card(self._row(owner,nonce))

    def inbox(self, owner):
        self._owner(owner)
        with self.store.transaction():
            cards = [self._card(r) for r in self.db.execute('SELECT * FROM owner_requests WHERE context=? AND owner=? ORDER BY rowid DESC LIMIT 20',(self.session.context,owner))]
            return [{k:c[k] for k in ('request_id','owner','action','state','revision','reason')} for c in cards]

    def resolve(self, owner, nonce, review_digest, choice, signed=None):
        if choice not in ('approve','decline','defer'):
            raise Denied('Choose approve, decline or defer explicitly')
        with self.store.transaction():
            row = self._row(owner,nonce)
            if self.db.execute('SELECT 1 FROM owner_request_replacements WHERE original=?',(nonce,)).fetchone():
                raise Denied('Superseded review cannot be approved, declined or deferred again')
            if row['state'] not in ('pending','deferred'):
                raise Denied('Request already resolved; approval needs cancellation/revocation, not a later decline')
            card = self._card(row)
            if type(review_digest) is not str or card['review_digest'] != review_digest:
                raise Denied('Review changed; reopen the exact request before deciding')
            if choice == 'approve':
                self._current(card['decision'],card['envelope'])
                if type(signed) is not dict or set(signed) != {'decision','signature'} or signed['decision'] != card['decision']:
                    raise Denied('Approval must be the exact owner-signed reviewed decision')
                if card['action']=='send': self.registry.verify_delivery(signed,card['envelope'])
                else: verify_owner(self.registry.owner_roots[owner],DOMAIN,card['decision'],signed['signature'])
                state = 'authorized'
            else:
                if signed is not None: raise Denied('Decline/defer cannot carry an approval')
                state = 'declined' if choice=='decline' else 'deferred'
            self.db.execute('UPDATE owner_requests SET state=?,revision=revision+1,signed=? WHERE nonce=?',
                            (state,canonical(signed) if signed is not None else None,nonce))
            return self._card(self._row(owner,nonce))

    def reconcile_request(self, owner, nonce):
        """Repair UI status after execution committed. Never execute or send here."""
        with self.store.transaction():
            row = self._row(owner,nonce)
            if row['state'] in ('authorized','submitted') and not self._withdrawal(nonce):
                decision, message = self._validate(json.loads(row['decision']),json.loads(row['envelope']))
                committed = self.db.execute('SELECT fingerprint,result FROM owner_decisions WHERE nonce=?',(nonce,)).fetchone()
                if committed:
                    if committed['fingerprint'] != digest({'decision':decision,'envelope':message}):
                        raise Denied('Execution ledger disagrees with the reviewed request')
                    self.db.execute("UPDATE owner_requests SET state='submitted',result=? WHERE nonce=?",(committed['result'],nonce))
            return self._card(self._row(owner,nonce))

    def submit(self, owner, nonce):
        card = self.reconcile_request(owner,nonce)
        if card['state']=='withdrawn': raise Denied('Owner authorization was permanently withdrawn')
        if card['stored_state']=='submitted': return card
        if card['stored_state']!='authorized': raise Denied('An unresolved or declined request cannot execute')
        row = self._row(owner,nonce)
        signed = json.loads(row['signed'])
        if card['action']=='send': self.box.enqueue(signed,card['envelope'])
        else: self.gateway.apply(signed)
        # Crash here is safe: the same nonce is in the durable execution ledger.
        return self.reconcile_request(owner,nonce)

    def delivery(self, owner, nonce):
        """A truthful owner status view. It does not reconcile, retry or process."""
        row = self._row(owner,nonce)
        if json.loads(row['decision'])['action']!='send': raise Denied('Request is not a message')
        status = self.box.status(nonce)
        labels = {'queued':'Approved and queued; not dispatched','dispatched':'Outcome uncertain; check receipt before any retry',
                  'received':'Recipient receipt verified; not processed','processed':'Received and processed locally',
                  'blocked':'Blocked before dispatch','received_blocked':'Received; processing blocked',
                  'stopped_uncertain':'Stopped; earlier outcome uncertain, receipt checks still allowed'}
        eligible, reason = status['state'] in ('queued','dispatched'), None
        if eligible:
            try:
                decision, message = self.registry.verify_delivery(json.loads(self.box._row(nonce)['signed']),json.loads(row['envelope']))
                now = int(self.store.clock())
                if not decision['issued_at'] <= now < decision['expires_at']: raise Denied('Owner send approval expired')
                self.box._current_permission(decision)
                self.registry.permits(owner,decision['target']['recipient'],now)
                self.session._restore()._validate(message)
            except Denied as exc: eligible, reason = False, str(exc)
        return {**status,'label':labels[status['state']],
                'can_check_receipt':status['attempts']>0,'can_start_attempt':eligible,'attempt_blocker':reason,
                'can_process':status['state']=='received','calendar_booked':False}

    def next_step(self):
        """Prepare the next fictional review, never infer approval or retry a send.

        Refusals/deferred requests are surfaced, not silently replaced. This guide
        is deliberately single-meeting and conservative; explicit prepare remains
        available for a new owner-requested review after circumstances change.
        """
        # A crash can leave authorized UI state after execution committed. Repair
        # only from existing ledger evidence before interpreting stale reviews.
        for row in list(self.db.execute("SELECT owner,nonce FROM owner_requests WHERE context=? AND state='authorized'",(self.session.context,))):
            self.reconcile_request(row['owner'],row['nonce'])
        with self.store.transaction():
            broker = self.session._restore()
            if broker.cancellation:
                uncertain = self.db.execute("SELECT sender,nonce FROM encrypted_outbox WHERE context=? AND state IN ('dispatched','received','stopped_uncertain') ORDER BY rowid LIMIT 1",(self.session.context,)).fetchone()
                if uncertain:
                    return {'kind':'delivery','owner':uncertain['sender'],'cancelled':True,**self.delivery(uncertain['sender'],uncertain['nonce'])}
                return {'kind':'stopped','reason':'Meeting cancelled. No unresolved attempted deliveries remain in this guided fixture.'}
            pending = self.db.execute("SELECT owner,nonce FROM owner_requests r WHERE context=? AND state!='submitted' AND NOT EXISTS (SELECT 1 FROM owner_request_replacements l WHERE l.original=r.nonce) AND NOT EXISTS (SELECT 1 FROM owner_authorization_withdrawals w WHERE w.source_nonce=r.nonce) ORDER BY rowid LIMIT 1",(self.session.context,)).fetchone()
            if pending:
                return {'kind':'request','card':self._card(self._row(pending['owner'],pending['nonce']))}
            delivery = self.db.execute("SELECT sender,nonce FROM encrypted_outbox WHERE context=? AND state!='processed' ORDER BY rowid LIMIT 1",(self.session.context,)).fetchone()
            if delivery:
                return {'kind':'delivery','owner':delivery['sender'],**self.delivery(delivery['sender'],delivery['nonce'])}
            next_pair = None
            for owner in self.session.meeting.participants:
                for a,b in dict.fromkeys(((owner,self.session.meeting.coordinator),(self.session.meeting.coordinator,owner))):
                    row = self.db.execute('SELECT expires FROM contacts WHERE owner=? AND peer=? AND purpose=?',(a,b,self.session.context)).fetchone()
                    if row is None or row['expires']<=self.store.clock():
                        next_pair=(a,b);break
                if next_pair:break
            message = None
            if not next_pair and not broker.agreed:
                for agent in self.session.agents:
                    if agent.identity not in broker._received:
                        message=agent.preview_availability(self.session.meeting);break
                if message is None and broker._proposal is not None:
                    for agent in self.session.agents:
                        if agent.identity not in broker._offered:
                            message=broker.preview_proposal(self.session.registry[self.session.meeting.coordinator],agent.identity);break
                        if agent.identity not in broker._acceptances:
                            message=broker.preview_acceptance(agent);break
            complete=broker.agreed
        if next_pair:
            return {'kind':'request','card':self.prepare(next_pair[0],'pair',peer=next_pair[1])}
        if message:
            return {'kind':'request','card':self.prepare(message['sender'],'send',envelope=message)}
        return {'kind':'complete' if complete else 'stopped','reason':'All four accepted; no calendar booking.' if complete else 'No common candidate time. No new proposal is invented.'}
