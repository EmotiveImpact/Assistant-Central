# Exact conversation disclosure reviews

This local milestone prepares and authentically reinspects an **inert review** of
an exact, fictional OpenAI Responses request. It makes no provider request and
confers no disclosure, execution or spending permission. It is not wired to a
provider, runtime, bridge, server, UI or existing personal assistant.

## Scope and coordination

The conversation integration maintainer owns `disclosure_review.py` and the focused
review/expiry tests; an independent reviewer owns the separate boundary regression
tests. The base is local commit `9f3f843c80f77168600dba5de9da676fee4ead51`, tree
`ca15f561209e673ee8847784138c37bdfe2245cd`. Changes are confined to this new module,
new tests and this document. This local notice substitutes for draft publication
while remote writes are blocked. Nothing has been published or marked ready for
remote integration. No existing implementation, permission, workflow or UI changes
are part of this milestone.

## Host API

Import `ConversationDisclosureReviews` and `fixture_route` directly from
`conversation.disclosure_review`. Construct the wrapper with the genuine local
`ConversationLedger`. It adds no tables and has no persisted review cache.

1. `prepare(executor, session, binding, event_ids=[...], operation_id=...,
   route=fixture_route(...), review_deadline=...)` requires the executor's genuine
   current session and exact current conversation binding. Pass keyword arguments
   after the binding. The event list is explicit, ordered, non-empty and unique.
   The operation identifier is an opaque local correlation identifier, not an
   idempotency claim or execution reservation. The deadline is exclusive and at
   most 600 seconds ahead of the ledger's observed time.
2. Retain the returned `review_commitment` separately in trusted host state. The
   review is bounded JSON containing `body` and `review_commitment`. Its body
   contains the complete proposed request, public evidence for the complete
   declared ancestry, context and a closed source-disclosure plan. A host should
   clearly distinguish proposed provider input from ancestry shown only as review
   evidence. Do not treat model-produced JSON as an authenticated review decision.
3. `reinspect(reviewer, session, binding, review, expected_review_commitment)`
   requires the receiving source reviewer's **own** current session and binding,
   or the executor's own current session and binding. It reconstructs everything
   from the authoritative ledger and compares the complete review with the
   original independently retained commitment. Supplying a matching hash of
   modified JSON does not preserve that original commitment. Caller-supplied
   bodies, author maps, public projections and cached authority are not trusted.
4. Every returned full review goes to the authenticated actor only. Preparation
   may check other required reviewers' policy eligibility while they are logged
   out. It does not impersonate those people or return reviews directly to them.
   They obtain their own full review only through authenticated reinspection.

There is deliberately no approval, signing, import, consumption, dispatch,
credential, account activation or message-sending method. `SourceGrantLedger` is
not instantiated. Its independent transaction is not dispatch permission, and the
existing runtime's rejection of substituted inherited source authority is unchanged.
Source plan labels, fixed snapshot revisions and commitments are inert bindings,
not claims that a future grant or provider adapter would accept this review.

## Exact request and public profile

The route pins OpenAI, HTTPS endpoint `https://api.openai.com/v1/responses`, POST,
`openai-responses-json-v1`, profile `conversation-selection-fixture-v1`, and account
`unconfigured-fixture-only`. Only the public fixture model names `gpt-4.1-mini`
and `gpt-4.1` are accepted; this allowlist is not a provider availability claim.
The caller selects a bounded output ceiling of 16–4096 tokens. This is a resource
ceiling, not a currency-denominated spending authorisation.

The public purpose and instructions are fixed in the module. Arbitrary private
purpose text, instructions, model labels, account selectors and route extensions
are not accepted. Content enters the proposed request only through selected,
provenance-bearing ledger messages. Each selected message contributes one user
input-text item in the supplied selection order, preserving its exact text.
An ancestor that was not explicitly selected is **not** silently added to input.
The request fixes empty tools, `tool_choice: none`, background/store/stream false
and disabled truncation. Proposed input remains untrusted data.

The commitment covers complete canonical request JSON, including model,
instructions and settings; route/account/profile/format; ordered selection;
conversation and policy generation; source-reviewer and executor current epochs;
review deadline; fixed purpose; executor and provider recipient; complete public
source projections and graph/provenance digests. Provider recipient is always the
executor. Every immutable event snapshot uses revision 1. The full returned
envelope, including evidence, plan, request and commitment, must fit 16 KiB.

## Authoritative provenance and visibility

Within one existing conversation transaction, the implementation verifies selected
signatures and every declared ancestor, checks retained source digests, same-room
membership of each event and strict earlier-sequence references. Diamond ancestry
is deduplicated without dropping either original or derived authors. The closure
has at most 16 unique events; this bound is enforced before traversing beyond the
limit and before recursive visibility checks. Direct reference lists are also
bounded. Existing bounded canonical helpers impose a maximum nesting depth of 8,
a structural node limit and a 16 KiB byte limit. Oversized combined evidence or
envelopes are refused, never shortened, silently dropped or partially returned.

Required source reviewers are **all authors in that closure**, not the entire room
roster. The executor has a distinct review obligation even when also a source
author. Every required source reviewer and the executor must currently be allowed
to see the entire selected payload and all ancestors. No invitation, history grant
or membership change happens automatically. An original author does not gain the
right to see another author's derived output merely by owning the original.
Failure yields no partial review, hidden text, hidden event identifiers, digests or
counts. Public evidence uses the ledger's authorised public projection, never full
signed bodies or historical recipient audiences.

The existing visibility algorithm is reused rather than reimplemented. The same
ledger transaction runs a complete reconstruction in `final_checks`, after its
final genuine authentication checks. It captures actor and coordinating storage
session deadlines. A separate outer expiry fence spans **all** reviewer scans and
the subsequent projection/envelope work, so an early reviewer's history grant
cannot expire unnoticed during a later reviewer's scan. This conservatively rejects
any active room-grant expiry crossing that interval, including unrelated or
overlapping grants. A fresh inspection may succeed if another valid path remains.

Policy changes, changed epochs, history-grant revocation/expiry, deadlines or any changed
selection, source, request or route invalidate an old review. Refused operations
retain the ledger's durable observed-time fence, including refusals during final
authentication. Rewinding the clock after a refusal cannot revive an old grant.
There is no claim of instantaneous wall-clock validation at SQLite commit.

## Trust limits

This is the existing trusted local-host contract with separately authenticated
fictional owners, encrypted local payloads and pinned signing identities. It is
not distributed end-to-end encryption, a production multi-owner service or proof
of independent human comprehension. The host can see plaintext during authorised
inspection, and copied review plaintext cannot be recalled.

A signature establishes authorship by a pinned local key, not real-world ownership
or semantic completeness of source declarations. Omitted/copy-pasted provenance
cannot be discovered by this module. Revision 1 applies to immutable retained
events; there is no global version oracle or remote withdrawal-freshness claim.
Database/host compromise, direct policy tampering and whole-backup rollback remain
outside the ledger trust model. Timing is not constant-time.

A review is not a bearer capability or signed evidence of anyone's approval. It
does not prove a previous preparation occurred, reserve an operation identifier,
record unanimous review, activate an account, authorise money, or supply a
single-use/remote exactly-once guarantee. Reinspection is a current authorised
view, not a replacement for future explicit source and executor disclosure
approval. Any future execution design must independently establish its transaction,
consumption and dispatch boundaries; this milestone intentionally supplies none.

## Verification

Run from the repository root with Python 3.11+ and `pilot/requirements.txt`:

```sh
python -B -m unittest discover -s conversation/tests -v
python -B -m unittest discover -s pilot/tests -v
python -B tools/verify_import.py
python -B -m conversation.demo
python -B -m conversation.proposals_demo
git diff --check
```

New focused tests use genuine separate local sessions and fictional data. They
cover exact request/owner bindings, nested and diamond ancestry, authorisation and
membership changes, malformed or modified sources, complete closure/envelope
bounds, final actor/coordinator expiry, multi-reviewer grant expiry, and durable
clock rollback. They also verify that payload, audit, grant and member tables are
unchanged, with only the existing clock fence permitted to advance. Mocks reject
signing, grant consumption, network calls, credential changes and automatic
permission writes. Passing tests do not constitute live provider acceptance.

Local verification completed: 169 conversation/proposal tests (including 42 new
focused disclosure tests), 378 pilot tests, both fictional conversation demos,
673 imported-file checks and 17 team manifest checks passed. Module import smoke
checks and staged whitespace checks passed. The independent reviewer separately
ran all 42 disclosure tests and all 169 conversation/proposal tests. These are
local fixture results, not remote CI, live account or provider acceptance results.
