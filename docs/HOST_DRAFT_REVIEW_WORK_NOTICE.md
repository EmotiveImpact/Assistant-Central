# Authenticated host draft review

Coordination only; no working implementation in this first commit.

The owner-review implementer owns the bridge review API and fixed local helper, a new workspace review facade/module, focused tests and this milestone's documentation. Workspace conversation controls retain ownership of their current server, app and page changes until an explicit handover.

Base: main, with the reviewed supported-host bridge (PR 20) and workspace/conversation controls (PRs 23 and 24) as development dependencies. No automatic merge or provider activation.

Goal: an authenticated owner can inspect exact inert host drafts and explicitly dismiss them. Queueing is not notification, consent, delivery or execution. No model-facing approval, history or new network listener. Host configuration pins the real owner fingerprint and current binding.

Verification: real SDK MCP draft creation, owner HTTP inspection and dismissal, cross-owner/session/digest/expiry/revocation negatives, stable duplicate decisions and restart, encryption and content-free logs, same-origin protection and inert accessible DOM. Hosted acceptance is required because local browser sockets are restricted.

## Implemented candidate

The optional single-owner workspace now lists current host-bound drafts, shows
exact immutable content and bindings, and records explicit encrypted local
dismissals. Current owner sessions, original leases, review digests, revocation,
expiry, clock fences and durable idempotency remain mandatory. The fixed local
helper distinguishes a known refusal from an uncertain committed outcome.

Local checks: 56 bridge tests and strict TypeScript, 21 workspace HTTP/config
checks, 45 UI/model checks, import integrity and 320 team/execution/integration
checks. The full pilot regression and exact-head hosted browser/isolation gates
are tracked separately; no unrun check is claimed as passing here. A backend
review found a post-commit helper-error classification issue, now fixed with its
independent regression retained. UI review also added interrupted-tab restoration
without clearing the uncertainty latch.

Only already-published product dependencies are composed. Unpublished
conversation-controls files are excluded. No merge or live activation.
