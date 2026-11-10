# Combined local owner workspace

The optional conversation controls and host draft review now share one local
workspace. Configuration is still explicit and both features remain disabled by
default. This is a trusted local coordinating host, not remote multi-owner hosting.

## Decisions and boundaries

- Construct `ConversationService` before `HostDraftService`. The outer draft
  service selects the currently authenticated local account, not the primary
  coordinator by assumption. Peer ingress remains primary-owner-only.
- Every person signs in with their own existing local account. The coordinating
  owner must keep a separate current session to unlock conversation storage.
  Coordinator logout or expiry blocks conversation retrieval without signing out
  another account or substituting its draft queue.
- Conversations keep explicit future-only joins and exact source-author history
  grants. Drafts keep their original owner, host session, conversation, recipient
  and lease bindings. Host review permits inspection and dismissal only.
- The shell and both panels share operation leases. Only the matching lease can
  release a pending operation. Navigation and privacy cleanup remove plaintext,
  but do not cancel or silently unlock an outstanding mutation. Old-session
  completions cannot release new-session operations or restore old plaintext.
- A selected panel that was hidden while another panel was pending is restored
  when idle and visible, with source/operation uncertainty intact. Restoration queued
  under an old session is refused. A plain runtime state read cannot clear another
  store's uncertainty. Host dismissal recovery requires the matching committed
  dismissal at the original exact binding and digest; pending/unavailable state
  remains inconclusive. Conversation uncertainty permits read-only inspection
  but holds all writes for that session because the current API cannot reconcile
  a lost request ID. Known read-only conversation POSTs remain retryable on read
  failure and cannot create a write hold; write paths cannot opt out of the fence.
  Session end discards its in-memory hold; it is not evidence
  that the operation failed. There is no automatic retry.
- Passive message refresh preserves an unsent draft and request ID only when its
  actor, session, conversation, membership epoch and policy generation match.
  Membership changes, privacy cleanup and session changes clear it. Submitted
  drafts cannot become a new request through passive refresh.
- Room, invitation and retained-grant inspection apply the existing final
  actor/coordinator deadline fence after the last authentication. Grant status
  updates at that final boundary; revoked/expired grant history remains available
  to a currently authorised issuer.
- Exact proposal primitives remain backend-only. No new proposal approval UI,
  model approval tool, model history access, source/provider disclosure,
  transport change, live account or external action is enabled.

## Disposable fixture

After installing the repository's pinned Python and bridge test dependencies:

```sh
python -B -m workspace_ui.owner_workspace_fixture --port 8778
```

The fixture creates fresh Alice, Bob and Carol local accounts, a conversation and
separate genuine SDK-produced Alice/Bob draft queues. Use account `alice`, `bob`
or `carol` with the public fixture password `Fictional conversation password`.
Keep Alice signed in in a separate browser context while inspecting conversations
as another account. All content and passwords are fictional test data. Temporary
accounts and keys are removed on normal exit. No provider is contacted.

## Local evidence

The composition was checked locally on 10 November 2026:

- 113 conversation tests and 378 pilot tests passed.
- 39 actual workspace HTTP/config tests passed, including eight combined tests.
  These use genuine disposable accounts and SDK queues, exercise cross-owner
  inspect/dismiss refusals, exact author grants/revocation, future-only joins,
  stale audience refusal, coordinator logout/expiry, default/independent feature
  configuration and recursive module retrieval over actual HTTP.
- 75 workspace and pilot JavaScript model tests passed, including 21 shared
  interruption/controller and scoped shell inspection checks, plus passive draft
  preservation checks. Inert-DOM
  tests validate state and event ordering, not layout or browser acceptance.
- 62 bridge tests and strict TypeScript passed.
- 84 team, 133 execution, 103 integration, 18 network-acceptance harness and 20
  isolation harness tests passed. Harness unit tests are not Docker/UID/network
  isolation acceptance.
- Import verification passed for 673 imported files and 17 team manifest entries.
- The existing actual pilot HTTP/UI contracts and 39 synthetic stdio checks
  passed. The archived consent prototype's full verifier passed using the existing
  pinned local Python dependency closure: 948 Python tests and all 15 DOM-model
  suites passed. The first attempt lacked `coincurve` on
  the default Python path; no archived source or dependency pins were changed.

These counts describe separate suites, not multiplied assertions or browser
coverage. A broad JavaScript glob initially included browser scripts without
their launch prerequisites; the explicit model command below is the passing
model run. The initial direct team discovery needed the repository's documented
`team/run_checks.py` runner, which then passed.

## Reproduce targeted checks

```sh
python -B -m unittest discover -s workspace_ui/tests -v
python -B -m unittest discover -s conversation/tests -v
python -B -m unittest discover -s pilot/tests -v
node --test workspace_ui/tests/conversations.test.mjs workspace_ui/tests/host_drafts.test.mjs workspace_ui/tests/operations.test.mjs workspace_ui/tests/projections.test.mjs pilot/web/tests/model.test.mjs pilot/web/tests/transfers.test.mjs
npm --prefix agent_bridge test
npm --prefix agent_bridge run check
python -B tools/verify_import.py
```

## Browser and release gates

`tests/owner_workspace.browser.test.mjs` is prepared for desktop and mobile
checks against a fresh combined fixture. It covers real account sessions,
owner-specific queues, a committed dismissal held across hash navigation and
visibility cleanup, cross-panel uncertainty, passive composer preservation,
audience changes and coordinator lock. Run it with Playwright and Chromium in
an authorised environment:

```sh
OWNER_WORKSPACE_URL=http://127.0.0.1:8778 \
OWNER_WORKSPACE_PASSWORD='Fictional conversation password' \
WORKSPACE_SCREENSHOT_DIR=/tmp/owner-workspace-evidence \
node workspace_ui/tests/owner_workspace.browser.test.mjs
```

The local launch failed before opening any page: Chromium reported
`socket() failed: Operation not permitted` and a read-only crash-report path.
No alternate sandbox flags, executor or permission bypass was attempted. The
script's syntax passes, but browser interactions and screenshots are unverified.
Existing conversation and host browser scripts remain available for their
separate fixtures. The owner-controls workflow now installs the pinned bridge
SDK closure, names model tests explicitly, and includes the combined browser
step. That step is prepared, not passed. Hosted CI and container acceptance have not run on this exact
composition because publication remains held.

The inherited conversation source-expiry race during final authentication was
fixed, independently reviewed and composed in base
`9f3f843c80f77168600dba5de9da676fee4ead51`. Its current lifetime and full source-lineage
checks are part of this local candidate, not an outstanding implementation gap.
The exact message-outcome method was separately accepted at
`f62694b19cee90f607bc460c1177d9df055cfcb9` before local composition. See
[conversation recovery](CONVERSATIONS.md) for the narrow UI scope and local tests.
Exact-head review, authorised publication and hosted/browser acceptance remain
release gates. Nothing here is a production-readiness or merge approval claim.
