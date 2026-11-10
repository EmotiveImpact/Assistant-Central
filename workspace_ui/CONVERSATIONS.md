# Local owner conversations

This optional workspace area is a **trusted local coordinating-host stage**, not
independent-device messaging. It reuses `ConversationLedger`; browser code does
not reproduce authorisation policy. Nothing in these controls sends history to
an assistant, a model or a provider. Messages remain inert, untrusted text.

## Host setup

Provision each owner separately using the existing interactive `pilot.server init`
flow. Do not use a real password in an argument, environment variable or JSON.
Close any other process using those owner stores. The trusted host runs all
accounts under one OS user: this is deliberately not isolated administration.
Each existing private owner directory must be mode 0700 with its private auth
store; all paths and public fingerprints are selected by the host, never by a
browser request. Public fingerprints must be independently pinned. This does
not establish real-world identity or enrol a remote assistant.

Create a separate existing mode-0700 ledger directory, then a mode-0600 JSON file
owned by the same user. Its schema is:

```json
{
  "version": "assistant-central-conversation-host/1",
  "directory": "/private/central/conversation-ledger",
  "actors": [
    {"directory": "/private/central/another-owner", "fingerprint": "64-character public fingerprint"}
  ]
}
```

The `--directory` owner is the coordinating storage owner and is added implicitly.
Use `python -m workspace_ui.server serve --directory /private/central/host-owner
--conversation-config /private/central/conversations.json`. The shell remains
loopback-only. Without this flag the original single-owner server is unchanged
and the Conversations area explains that it is disabled. No provisioning,
credential creation, arbitrary path selection or provider activation is exposed
through HTTP. Secondary owners do not inherit the primary owner's HTTPS transfer
configuration. Existing unauthenticated peer-mailbox ingress remains primary-only.

## Separate sessions, one coordinating host

Each person enters their existing local owner account name and password in their
own browser profile or private context. Blank account means the primary host
owner. Account names are not listed before authentication. Matching names alone
do not grant access; the chosen account must authenticate with its own password.
Normal workspace data and actions are routed to that owner's real `OwnerService`.
No token is stored in browser storage or reused as another actor's session.

The coordinating owner must independently remain signed in with a current
session in another browser context. Their last logout or session expiry locks
all conversation retrieval and mutations, even empty list/search operations.
Other owners' normal workspace sessions may remain valid. Restart locks every
account and discards pending history reviews. Unlock explicitly and review again.

All services run on the existing single owner worker. Authentication releases its
individual lock before entering the ledger, which uses its established globally
ordered locks. The facade does not manufacture sessions, retain passwords or keep
storage keys unlocked without a current coordinator session.

## Membership and history

- Create a stable conversation, invite a configured account, and have that account
  explicitly accept. Two active members form a direct conversation; expansion to
  a group preserves its ID. Rejoining starts a new membership epoch.
- New and rejoining members see only future messages. Lists use opaque conversation
  IDs, not previews, historical titles, sequence numbers or hidden message counts.
- Read and search return at most 25 visible messages per page. Next-page cursors
  must name a message currently visible to that actor. Selection-based context
  inspection is local-owner-only, with no model-facing tool or execution authority.
- A composer retains the exact membership epoch and policy generation shown when
  opened. Membership or grant-policy changes require fresh review before sending.
  A generated request ID prevents the same exact send being inserted twice.
- Select up to 25 of your own visible messages and name one current recipient,
  purpose and expiry (at most 24 hours). Inspect the exact words, source digests,
  recipient fingerprint, membership epoch and review digest before checking the
  confirmation and approving. Other authors need their own approval. Derived
  source checks remain the ledger's responsibility.
- A prepared review is not consent. The server retains the exact statement for at
  most ten minutes, bound to the preparing actor and their exact browser session.
  Changed audience, expired permission, another session, logout and restart fail
  closed. At most 16 reviews per actor and 128 overall are retained in memory.
- Issuers can inspect and revoke their own grants, including after removal from
  a room, via **My issued history grants**. Pages contain at most 50 statements;
  **Next older grants** finds older active grants without revealing other issuers.
  Revocation cannot recall copies already seen. The administrator cannot leave or
  transfer ownership in this stage.

## Interruption and disclosure boundaries

Conversation surfaces recheck at 15-second intervals and on focus. Unchanged
snapshots do not erase a draft. A passive refresh with new messages preserves
unsent text and its request ID only for the same actor, session, conversation,
membership epoch and policy generation. A submitted or uncertain draft is never
passively recreated as a fresh request. Changed access clears the current review/content;
a hidden document, leaving the area, logout or session expiry clears conversation
DOM. Previously seen text cannot be made unseen, and an idle disclosed snapshot
may remain visible until the next check. Approvals and sends always recheck policy
on the server, irrespective of what remains on screen.

Writes are never automatically retried. A lost response or failed post-write
inspection retains the source and operation identity, even across panel changes
and privacy cleanup. A basic workspace refresh or unrelated panel inspection
does not itself reconcile a conversation request. **Refresh saved state** also
performs an explicit read-only inspection when the hold is for one exact message.
Before the original send, the client computes SHA-256 over the ledger's canonical
UTF-8 request (sorted keys `kind`, `source_ids`, `text`, with source order preserved
and no Unicode normalisation). Ill-formed surrogates or unavailable hashing stop
the send. An in-flight hash holds the shared operation gate; navigation or privacy
cleanup before dispatch cancels that send without creating a recovery hold.

Only immutable, bounded metadata survives privacy cleanup: the original browser
session generation, authenticated principal, room, membership epoch, policy
generation, request ID and request digest. No message text, token or new browser
storage is retained in that ticket. The authenticated
`POST /api/conversations/{room}/message-outcome` route accepts exactly the original
binding, request ID and expected digest. It calls the reviewed read-only ledger
method; no send, grant, approval or provider/model call is repeated.

The client clears only that exact message hold after a committed result matches
the original author and room and its kind, text and ordered source IDs recompute
to the original request digest. The provenance digest is a separate commitment.
Both the original ticket and session must still match at completion. Returned
words are checked transiently and never inserted into an inactive/hidden panel or
saved in a recovery cache. Ordinary authorised history reads remain separate.

Absence is **inconclusive**, not rollback or permission to retry. Read failure,
wrong digest, revoked/expired access, a stale epoch/policy binding and coordinator
lock retain the hold. An inspection failure is a read failure, not a new uncertain
write, so the same exact inspection remains available. The client never replaces
the original binding with a fresh audience to clear the hold. Create, invitation,
join, removal and history-grant mutations still have no exact UI recovery and stay
conservatively held. Other panels and late old tickets cannot clear this source.
Ending the session discards its in-memory hold, not evidence of a failed operation;
reload does not recover the ticket and must not be treated as permission to replay.
A refresh may discard a local unsent draft. Browser tokens and in-memory exact reviews are
not durable. Pending invitations show the latest 50, with no hidden-message count;
act on newer invitations to reach older ones. The ledger caps conversations at
256, so the current conversation list covers its full supported room capacity.

This stage trusts the coordinating process and OS user, is not end-to-end encrypted
from that host, does not prove real people or independent assistant-host control,
and does not protect against host compromise/database rollback. Retained payloads
are encrypted to the coordinating owner's storage identity using the reviewed
ledger. Distributed replication, attachments, model history access and live
assistant wake/execution remain separate work.

## Verification

`python -m unittest discover -s workspace_ui/tests -p 'test_*.py' -v` exercises real
loopback HTTP with separate password-authenticated accounts. Ledger inspection
regressions live in `conversation/tests/test_inspection.py` and
`conversation/tests/test_message_outcomes.py`; browser-independent
validators and interruption gates use `node --test
workspace_ui/tests/conversations.test.mjs`. The dedicated owner-controls workflow
runs the disposable `workspace_ui.conversation_fixture` and actual desktop/mobile
Chromium against the backend. Local Chromium is unavailable in the development
sandbox; hosted results, exact commit/tree and independent review are reported
separately. Fictional fixture passwords are public test data, never real accounts.

The local recovery candidate adds real HTTP committed-response loss (a deliberately
closed response after commit), repeated exact reads with one stored message,
wrong digest/owner/room/binding, coordinator/actor expiry and generic read failure.
Component checks cover hashing failure, pre-dispatch privacy cleanup, hidden and
unrelated views, session/ticket races and no replay. The updated browser script
prepares committed recovery, failed-read retry and inconclusive-absence assertions;
those browser assertions have not run locally or on hosted CI for this candidate.
