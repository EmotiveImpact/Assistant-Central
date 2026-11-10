# Local exact message outcome work notice

Coordinator: local owner workspace maintainer, with independent integration review.
Base: 9f3f843c80f77168600dba5de9da676fee4ead51.

This is local-only coordination because GitHub publication is held. No draft PR,
remote write or alternate publication route is attempted. This first commit is a
coordination notice, not working implementation.

Claimed components: workspace_ui/conversation_service.py, conversations.mjs,
operations.mjs, app.mjs, focused workspace HTTP/component/browser test sources and
the conversation documentation. The separately owned frozen ledger outcome method
will be composed only after independent acceptance. No pilot, auth, provider,
bridge, transport or proposal implementation changes are in scope.

Goal: explicit authenticated inspection of one original message request after a
lost response, without replay. A bounded in-memory ticket retains its session,
principal, room, membership epoch, policy generation, request ID and canonical
content digest, never plaintext after privacy cleanup. Only an exact committed
result for that unchanged ticket may clear its conversation hold. Missing,
unavailable, stale or denied results stay inconclusive. Other mutations stay held.

Verification: canonical Unicode/escaping/source-order vectors against Python,
actual disposable local-owner HTTP, component interruption/session/visibility
checks, conversation and workspace suites, UI model/import/type checks. Browser
coverage will be prepared but not run: local Chromium cannot create sockets, and
the hosted workflow remains unrun while publication is held.

## Frozen local implementation

Independent review accepted ledger dependency
`f62694b19cee90f607bc460c1177d9df055cfcb9` (tree
`ded8c7feeb3ecc805024dfd6a44426d2fc7747e6`) before integration. The local merge is
`fecb698c06a80ddc91c275f1b4089e912ce5d38a` (tree
`670683ebae33694edd1c119cd0fab26ba6715e1b`). The new ledger method, its test file
and its work notice remain byte-identical to that accepted dependency. The
current cumulative ledger keeps the already accepted source-expiry guards.

The added owner route is the explicitly read-only
`POST /api/conversations/{room}/message-outcome`. Refresh saved state checks it
only for an original immutable message ticket; a generic runtime catalogue read
is insufficient. Author, room and recomputed exact request commitment must all
match, and only the same session and same source ticket can release the hold.
No recovered text is rendered or cached. Unsupported conversation mutations
remain held. Digest preparation is gated before dispatch and fails closed.

The implementation changes only the owner facade, conversation controller,
shared operation inspection and shell recovery wiring. There are no changes to
pilot, auth, provider, bridge, transport, proposal, CSS, fonts, layout or design
assets. Existing dependencies were reused through a temporary local symlink;
no package or lockfile was changed. No GitHub action or publication was attempted.

## Local verification

These checks ran on the cumulative implementation, not the earlier standalone
ledger branch:

- All 147 conversation/proposal tests passed (136.8 seconds).
- All 45 workspace HTTP tests passed (88.2 seconds), including six new exact
  message-outcome cases with disposable Alice/Bob/Carol owner accounts. The
  committed-response-loss case closes the actual HTTP response after commit and
  proves two read-only inspections leave one append and one unchanged event.
- All 87 explicitly named UI/model tests passed. They include Python/JavaScript
  canonical UTF-8 and digest agreement, ordered sources, invalid surrogates,
  failed hashing, privacy cleanup before dispatch, lost response, inconclusive
  absence, read retry, hidden/unrelated views, stale tickets and changed sessions.
- All 378 pilot tests passed (157.7 seconds).
- All 62 bridge tests and TypeScript `tsc --noEmit` passed.
- Import manifests verified all 673 imported files and 17 team entries.
- Both `conversation.demo` and `conversation.proposals_demo` passed with fictional
  data and no live provider or external execution.
- Shell/controller module and all prepared browser-test syntax checks passed.
  `git diff --check` passed. Protected implementation paths were checked unchanged.

The updated actual-browser test source prepares committed recovery, a failed
read-only inspection followed by a successful exact read, and absent/inconclusive
outcomes without replay. Those browser assertions were **not run**. No browser
was launched in this lane, no screenshots were produced, and the hosted workflow
remains unrun while publication is held. The known ordinary local Chromium
socket limitation was not bypassed. This is local test evidence only, not hosted,
distributed, real-person, real-assistant, production or merge acceptance.
