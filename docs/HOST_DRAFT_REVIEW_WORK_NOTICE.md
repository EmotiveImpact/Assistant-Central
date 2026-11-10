# Authenticated host draft review

Coordination only; no working implementation in this first commit.

The owner-review implementer owns the bridge review API and fixed local helper, a new workspace review facade/module, focused tests and this milestone's documentation. Workspace conversation controls retain ownership of their current server, app and page changes until an explicit handover.

Base: main, with the reviewed supported-host bridge (PR 20) and workspace/conversation controls (PRs 23 and 24) as development dependencies. No automatic merge or provider activation.

Goal: an authenticated owner can inspect exact inert host drafts and explicitly dismiss them. Queueing is not notification, consent, delivery or execution. No model-facing approval, history or new network listener. Host configuration pins the real owner fingerprint and current binding.

Verification: real SDK MCP draft creation, owner HTTP inspection and dismissal, cross-owner/session/digest/expiry/revocation negatives, stable duplicate decisions and restart, encryption and content-free logs, same-origin protection and inert accessible DOM. Hosted acceptance is required because local browser sockets are restricted.
