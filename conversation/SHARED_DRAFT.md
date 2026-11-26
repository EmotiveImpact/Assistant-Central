# Shared drafts

`conversation/shared_draft.py` gives assistants a shared draft beside the
conversation: a plan, itinerary or reply that everyone works on together, which
only becomes final when every person approves the same exact version.

It is a thin assistant-facing layer over [exact shared proposals](PROPOSALS.md):

- An assistant can **start** a draft, **revise** its own owner's draft (a new
  revision, which clears every approval), or **suggest** changes to another
  person's draft, which appear as a separate draft beside it.
- An assistant can **view** a draft and **list** the latest revision of each.
- An assistant can **never approve**. Each person approves the exact current
  revision with their own session, in Assistant Central.
- A draft is `final` only while it is the latest revision, the people in the
  conversation are unchanged, it has not expired and everyone has approved it.
- A final draft is agreed text only. It sends, runs and pays for nothing.
- Someone who joins later cannot read earlier drafts, and a roster change stops
  an old draft from becoming final.

## Assistant tools

When the host passes a `DraftAccess` to `mission_approvals.server.build_server`
as `shared_drafts`, the assistant gets `start_draft`, `revise_draft`,
`view_draft` and `list_drafts`. The lease and owner session come from the host.
