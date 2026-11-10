# Delivery decisions for review

10 November 2026. This is the product/engineering decision list for the integrated
local pilot, not a record of production acceptance. The
[delivery guide](DELIVERY.md) records the accepted main revision and the
remaining functional/live gates. Each choice below states the reason and the alternative or remaining limit.

## Authority and storage

1. **Keep owner authority outside model tools.** Source disclosure, task release,
   recipient acceptance, execution and final-result review are distinct exact
   decisions. A broad approval or lead assistant cannot act for another owner.
   This adds review steps instead of letting conversational agreement silently
   become permission. [Runtime](../pilot/RUNTIME.md).

2. **Authenticate local accounts without claiming verified people.** Password
   sessions and pinned signing keys identify provisioned local accounts. They do
   not prove a human's identity, independence or comprehension. Peer fingerprints
   need independent verification; model-selected names are never authority.
   Real-person enrolment remains a separate product/operational choice.
   [Authentication](../pilot/AUTH.md).

3. **Keep useful-work rehearsal synthetic until a live route is approved.** A
   fixed opt-in fixture exercises accepted task → approved run → retained result
   → reviewed return. It avoids undisclosed provider calls or spending. The
   alternative, activating a real account to make a demo look complete, is not
   part of this candidate. [Work loop](../pilot/WORKFLOW.md).

4. **Preserve identity during password maintenance.** Rewrap the same signing and
   encryption keys using the current password, invalidate sessions and lock the
   vault. Replacing keys would break peer pins; retaining sessions would weaken
   logout/revocation. Use a private stopped-service terminal. Lost-password
   recovery and identity rotation are not supplied by this flow.
   [Password maintenance](../pilot/PASSWORD_MAINTENANCE.md).

5. **Encrypt payload columns while retaining ordinary SQLite transactions.**
   Context-bound X25519/AES-GCM envelopes protect runtime/audit/provider/workflow
   content. Public-key sealing permits already-dispatched late results after
   logout, but is not writer authentication. Whole-file encryption was not added;
   metadata, unlocked-host access and backup rollback remain exposed.
   [Storage](../pilot/STORAGE.md).

6. **Make storage upgrades explicit and offline.** Validate the exact known
   schema, bound input and publish only a verified encrypted replacement. Refuse
   unknown schema and plaintext fallback rather than guessing how to migrate.
   Stop every store-owning process: the bridge version marker cannot fence an old
   binary that already opened the store. Replacement is not secure erasure of
   blocks or backups. [Pilot migration](../pilot/STORAGE.md#existing-plaintext-stores)
   and [bridge upgrade](../agent_bridge/OWNER_REVIEW.md#storage-upgrade-requires-an-offline-stop).

## Transport, interface and supported hosts

7. **Send only original retained packets, with explicit bounded retries.** Commit
   uncertainty before bytes leave; do not re-sign, extend expiry or automatically
   resend. Keep TLS certificate/hostname verification and normal network checks.
   A quarantine ACK, signed receipt, recipient decision and execution result are
   different facts. Cancellation cannot recall in-flight bytes.
   [HTTPS exchange](../pilot/HTTPS_EXCHANGE.md).

8. **Recover only the original cached receipt.** Missing retained receipt state
   is unavailable/corrupt state, not a reason to mint a new receipt on duplicate
   import. This preserves exact identity and expiry instead of turning recovery
   into renewed authority. The fix is integrated on main through the reviewed transfer composition.
   [Receipt recovery](CACHED_FILE_RECEIPT_RECOVERY.md).

9. **Accept the combined interface, not independently green screens.** Central
   reuses transfer controls and one authenticated owner context. Source-specific
   operation identities prevent an unrelated refresh or late response from
   clearing a pending/uncertain operation. Navigation and privacy cleanup must
   discard content without treating an interrupted write as cancelled. This is
   more conservative than queueing writes or silently retrying. The accepted composition passed its
   real Chromium flows; later changes require fresh checks. [Workspace](../workspace_ui/README.md).

10. **Keep three levels of isolation evidence separate.** Shared-loopback
    containers test mount/process/Unix-permission boundaries. Four distinct
    container networks add real TLS transport on one trusted host. Independent
    physical hosts and owners are a further acceptance test, not an inference
    from either container result. [Isolation](../isolation/README.md) and
    [network acceptance](../network_acceptance/README.md).

11. **Use official SDK paths without claiming personal-assistant connectivity.**
    OpenAI Agent/Runner runs deterministic model responses; Cursor/Grok SDK uses
    its supported no-model tool path, both through real MCP. Host configuration
    binds owner/session/room outside model arguments. The only model tools are
    inert `create_task_draft` and scoped status. This proves an integration seam,
    not two-assistant dialogue or access to existing personal accounts.
    [Bridge](../agent_bridge/README.md).

12. **Limit the owner draft queue to inspect/dismiss within the original lease.**
    Default-disabled authenticated controls show exact content and bindings;
    dismissal records no task consent, receipt or execution. The lease is at
    most 15 minutes and never renewed implicitly. An unavailable connection is
    not an empty successful inbox. A durable archival queue would need separate
    policy. Sample time after acquiring the write lock, recheck admission/expiry
    and recognise reserved schema prefixes literally so contention or unknown
    tables cannot bypass the intended boundary. [Owner draft review](../agent_bridge/OWNER_REVIEW.md).

## Conversations and exact review

13. **Start with one trusted durable coordinator.** Encrypted payloads, signed
    immutable messages and genuine separate local sessions make the policy
    inspectable before adding distributed replication. Every operation also
    requires an unlocked coordinating owner. This host can see authorised
    plaintext; distributed end-to-end encryption and hostile-tenant isolation
    are not claimed. [Ledger](../conversation/README.md).

14. **Make new membership future-only and old history author-controlled.** Every
    accepted/rejoined membership has a fresh epoch. Only the original author can
    grant exact earlier messages to a named current epoch and local-only audience.
    An administrator cannot share others' history, and rejoining does not revive
    earlier rights, even to one's own old messages. Automatic whole-room history
    would be simpler but would broaden disclosure without exact author approval.
    [Owner conversation controls](../workspace_ui/CONVERSATIONS.md).

15. **Check complete declared ancestry and current authority on every derived
    read.** Quotes, summaries, context, proposals and disclosure reviews recheck
    transitive sources; one author's grant cannot grant another author's derived
    output. Expiry/final-authentication fences and durable observed time prevent
    observed expiry from reviving after restart/clock rewind. Conservative
    refusal during a grant-expiry scan is preferred to returning partially stale
    content. Omitted copy-pasted provenance remains undetectable; this is not a
    semantic information-flow proof. [Ledger limits](../conversation/README.md#important-limits).

16. **Keep conversation controls optional and separately authenticated.** Trusted
    host configuration selects existing accounts; each owner uses their own
    session and the coordinator stays independently unlocked. No HTTP account
    provisioning, automatic history grant or provider access is added. This avoids
    silently making a single-owner workspace into a public multi-tenant service.
    [Host setup](../workspace_ui/CONVERSATIONS.md#host-setup).

17. **Resolve an uncertain message by exact read-only inspection.** Retain a
    bounded, session-bound ticket containing the original room, author, epoch,
    policy generation, request ID and canonical request digest, not plaintext or
    bearer tokens. A matching signed, currently visible local message can clear
    only that message's hold. An absent result is inconclusive; a history page,
    new binding, reload or unrelated panel cannot authorise replay. Hashes can
    expose guessed low-entropy text and are not secrets. Other uncertain mutation
    types still need conservative recovery. [Exact inspection](../conversation/README.md#inspect-one-uncertain-message-outcome).

18. **Require every frozen member to approve an exact proposal revision.** The
    proposer signs authorship, not consent. New revisions start with no approvals;
    a withdrawal cannot be reversed by retrying that revision. Current roster,
    epochs, policy, expiry and source visibility determine whether retained
    signatures still count. Unanimity means local discussion agreement only,
    not a contract, payment, execution or provider permission. This replaces vague
    majority/chat ratification with an auditable primitive; the proposal UI is
    still unbuilt. [Shared proposals](../conversation/PROPOSALS.md).

19. **Compile the final disclosure review before asking anyone to approve it.**
    Reconstruct the selected immutable messages and all declared ancestors from
    the authoritative ledger; use only authorised public projections, never
    historical recipient audiences. Every source author and the executor must
    already be allowed to see the entire review. Each later reviewer must use
    their own authenticated reinspection. Automatic grants or partial redactions
    would change what people are approving and are deliberately excluded.
    [Disclosure reviews](../conversation/DISCLOSURE_REVIEW.md).

20. **Use a fixed, bounded fictional provider profile for this compiler.** Pin
    the complete request, route, account placeholder, output ceiling, audience,
    epochs and review deadline. Limit the complete declared closure to 16 events
    and the whole envelope to 16 KiB; reject excess rather than truncate. Selected
    messages alone enter proposed input; unselected ancestors remain review
    evidence. Arbitrary private instructions/routes are excluded. A token bound
    is not spending approval. Prepare/reinspect neither signs nor dispatches and
    is not yet wired to runtime, MCP, server or UI.

21. **Keep source grants standalone until dispatch is atomically integrated.**
    Source authors and the executor need distinct exact approval of the final
    content/destination. Consuming a signed grant in a separate transaction is
    not bearer authority to call a provider later. Bind consumption to the
    irreversible attempt and uncertainty fence instead of introducing a check/use
    gap. The compiler creates no grant, consent record or provider permission.
    [Source grants](../pilot/SOURCE_GRANTS.md).

## Research and delivery strategy

22. **Keep upstream research inert, pinned and licence-aware.** Sixteen source
    snapshots preserve revisions, omissions and notices without running upstream
    agents/installers. Research is not dependency adoption. No verified public
    Weldra Parley source was found; ericscalibur/Parley declared ISC in metadata
    but lacked a licence/notice file at the inspected revision, so neither
    implementation was copied. [Pinned findings](https://github.com/EmotiveImpact/Assistant-Central/blob/8bb93f6f909202c3915df1827626d52027d51453/research/PARLEY_FINDINGS.md).

23. **Borrow interaction patterns, not weaker authority assumptions.** Private
    briefs, shared rooms, exact reviews, correlated human questions and body-free
    wake/cursor patterns are useful Parley-inspired directions. Bearer-room
    access, RAM-only history, automatic provider disclosure and unbound
    ratification are not adopted. Durable supported-host wake/result delivery
    remains work, not an implied feature of the local ledger.

24. **Keep acoustic transport optional and off the critical path.** Researched
    ggwave rates of roughly 8–16 bytes per second may suit bounded pairing/fallback
    experiments, not private transcripts or a faster assistant language. Bluetooth
    is radio, not this acoustic channel. Neither replaces application encryption,
    authentication, replay protection or visible owner intent.
    [Transport research](https://github.com/EmotiveImpact/Assistant-Central/blob/8bb93f6f909202c3915df1827626d52027d51453/research/FINDINGS.md#ggwave-and-gibberlink-optional-acoustic-transport).

25. **Prefer measured integration over a rewrite or premature launch.** Keep
    Python orchestration, evaluate Rust only at a measured boundary and test the
    actual cumulative revision. Preserve design ownership instead of duplicating
    unrelated visual changes. Older green branches and local tests cannot replace
    the latest browser/hosted, independent-owner or operational acceptance.
    [Ordered roadmap](../ROADMAP.md#ordered-delivery-dependencies).

## Decisions still needed before live delivery

- **Product and participating owners:** choose the first two-owner workflow,
  independently controlled hosts and supported existing assistant sessions.
  Decide which historical messages, if any, each original author wants to share.
- **Product and security maintainers:** agree the owner-facing proposal/disclosure
  review and uncertain-operation recovery experience before connecting execution.
  Choose how exact source approvals and executor approval commit with dispatch.
- **Account owner:** approve the exact live provider/account, disclosure audience,
  cost limit and credentials route. Fixture model names and SDK tests make no
  account-availability or billing commitment.
- **Operations and security maintainers:** choose hosting/certificates, key
  recovery/rotation, metadata/retention/deletion policy, backups and incident
  response. Decide how to validate independent-host custody and obtain external
  security review before real data.
- **Release maintainer:** preserve the accepted baseline and require applicable
  exact-revision hosted/browser/container acceptance for later changes. Treat
  live deployment as a separate decision.
