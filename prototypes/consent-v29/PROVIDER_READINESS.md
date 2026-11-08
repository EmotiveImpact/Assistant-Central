# Provider integration readiness

This is an acceptance plan, not an installer or a claim that any provider is
connected. It authorizes no account access, messages, identity creation, host
configuration changes, relay connection or publication. Current execution stays
offline, with fictional people and disposable fixture keys.

## Preserve the product boundary

The product connects people's assistants across providers for scoped tasks.
Scheduling is one capability adapter. A provider name in an identity reference
does not establish host compatibility, authenticate a person or grant authority.
A relationship may help an owner choose a contact; it does not permit private
data disclosure or tool execution.

An agent adapter is a lower-trust consumer. Its proposed message is data for
review, not an owner instruction. A received message, sender signature, link or
attachment is likewise not owner authority. The owner control interface must
remain separate from the agent interface. A host adapter must not forward the
trusted fixture executor's entire command surface to a model.

The current capabilities carry inert bounded text (`bounded-text-exchange-v1`)
or resource-list text and HTTPS-shaped references (`public-resource-shortlist-v1`). No resource is retrieved or verified. The capability
does not allow web browsing, purchasing, calendar access or other tools. Actual
agent execution requires a separately defined local permission policy.

## Evidence levels

1. **Offline application proof:** a synthetic task passes exact owner review,
   scoped identity binding, encrypted durable delivery, receipt and processing
   tests. This is the current demonstrated level. DOM-model checks do not count
   as real-browser acceptance.
2. **Native tools proof:** the specific installed host version actually loads
   and calls the reviewed adapter using its supported mechanism. A standalone
   Python process or valid configuration file is not this proof. Until tested,
   native tools remain unverified, not "tools-only ready."
3. **Consented private roundtrip:** two explicitly selected test identities
   exchange one approved synthetic task over a selected transport. Record each
   endpoint's receipt and processing independently. A relay connection or send
   acknowledgement alone is insufficient.
4. **Host wake proof:** the exact host demonstrably handles idle, busy and
   authorized-restart conditions, plus an isolated unauthorized-sender control.
   Tools and automatic wake are separate capabilities. If native tools work but
   wake does not, report tools-only. Do not add hidden polling or bypass host
   restrictions to manufacture a wake result.
5. **Operational readiness:** authenticated owner enrollment, persistent key
   custody and recovery, real relationship/contact management, revocation,
   retention and access policy, abuse controls, concurrency and load behavior,
   deployment operations and an independent security review are still required.
   No earlier level implies this level.

## Decisions required before any live pilot

- Select one concrete host, its version, operating system and supported
  project-scoped adapter mechanism. Do not assume compatibility with Claude,
  dot, Hermes or another host from a label or common protocol name.
- Select the two specific test identities and which owners control them. Decide
  the approved pairing and disclosure scope. No wildcard contacts, automatic
  friend import, public discovery or unsolicited messages.
- Decide the supported owner authentication and key-custody path. Disposable
  fixture keys prove key possession only. Reopening a database while the same
  keys remain in a live process is not recovery after losing those keys.
- Select the relay or other transport, data destination and test content. Review
  any required terms, account or persistent-access changes before taking them.
- Decide whether the first pilot needs tools on demand only or supported wake.
  Do not broaden the scope when the chosen host cannot provide it.
- Review exact configuration changes and permissions. No global configuration
  overwrite, secrets in a repository, exposed local port or weakened TLS.

Product naming, distribution model and the license for newly written project
code are separate product decisions. The upstream license notices already in
the project must remain intact regardless of those choices.

## Minimum negative controls for an adapter

- A caller cannot choose a different actor, context, recipient or capability by
  adding fields or reusing another caller's proposal identifier.
- Proposal creation cannot pair, approve, renew, submit, dispatch, process,
  withdraw an authorization, export a key or read another owner's review.
- Exact retries return the historical proposal. A changed payload under an
  existing idempotency key is rejected. Declined or withdrawn work is not
  silently recreated under a new key.
- Inbound data is disclosed only to the intended actor after the exact message
  has been processed. Queued delivery and receipt alone do not make it visible.
- A result is linked to the exact processed request, with its original limits.
  Payload text cannot expand permissions, choose a tool or enroll a contact.
- Unknown delivery stays uncertain. Neither a timeout nor a missing receipt
  alone proves nondelivery or authorizes another send.
- Restart, replay and concurrent calls do not duplicate owner actions or lose
  historical evidence. Storage exhaustion fails closed without implicit purge.

These are acceptance requirements, not a claim that every production scenario
has been exercised. Individual checkpoint verification records identify the
tests actually run. A JSON allowlist and Python audit hook are not an operating
system sandbox against code that can access the same interpreter or files.

## Upstream evidence and limits

Reviewed source: A4A `safe-connect.md` pinned to commit
`6b111e3fb6fdf61f0e790ae84e2db86c5bb86b7e`:

https://github.com/a4a-network/a4a/blob/6b111e3fb6fdf61f0e790ae84e2db86c5bb86b7e/docs/onboarding/safe-connect.md

That document labels its flow prerelease, distinguishes a read-only connect plan
from installation and identity creation, separates native tools from automatic
wake, and requires exact contacts and owner consent. These are upstream design
claims and useful acceptance criteria, not evidence that the current prototype
has installed or exercised its full MCP server. Its instructions were read, not
executed. Host support and source provenance must be rechecked for the eventual
chosen version.

Only the unchanged upstream files recorded in `UPSTREAM.json` are vendored here.
The full upstream client, MCP server and relay have not been copied or executed
as part of this prototype. No native host, relay or real-provider test has run.

The v15 two-task workspace adds offline isolation evidence only. Its task catalog,
console and adapter factory are trusted local fixtures, not a relationship
registry, task discovery service, authenticated host or browser product. Reused
fictional Alice/Bob labels do not merge identity or owner authority across tasks.


The v16 stream layer adds bounded LF framing and real local anonymous-pipe
fault tests. It does not select or install an actual stdio host, launch an exposed
service, authenticate callers, add wake support or enforce OS isolation. Its
fixed task/actor session still comes from trusted composition; all owner controls
stay outside the caller stream. Host acceptance also requires resource deadlines,
process lifecycle and trusted diagnostic routing not implemented by this helper.
See HOST_PROTOCOL.md for response-loss uncertainty and framing limits.


The v22 relationship task groups are an explicit temporary organization and
local stop mechanism, not a persistent contact registry or person/provider
verification. Grouping exact contexts does not merge their keys or grants. A
stop does not notify remote peers, recall data, preempt started actions or block
a person across unrelated tasks. These boundaries must remain explicit before
selecting any actual host or relationship identity system.


The v25 opt-in continuity fixture provides informational historical possession
proofs linking independent task-owner keys to a disposable fictional anchor. It
creates no real owner account, provider identity, trusted contact, persistent
credential or task authority. Local recognition must not be mistaken for live
possession or current permission. A real host still needs separately selected
authentication, key custody, contact consent and lifecycle rules.


The v26 scripted-client walkthrough extends offline application evidence to two
actual local client processes using the restricted protocol. Its control channel
and synthetic simulation are fixture orchestration, not provider interoperability
or human-consent evidence. Neither clients nor launcher install a native host,
create a socket, connect a relay, poll for work or add automatic wake. The live
pilot decisions and acceptance levels above remain unchanged.


The v27 mixed Python/Node fixture independently exercises local encoding, framing,
negotiation and lifecycle in both actor assignments. It adds language compatibility
evidence, not native tools, authenticated provider identities, live transport or
host wake. All real-host and owner-custody choices above remain open. A focused
201-test review found no new confirmed routed defect within the trusted-host
fixture model; it does not replace independent production security review.


The v28 optional SDK-backed adapter addresses legacy metadata/lifecycle compatibility
in decoded memory streams. Python MCP SDK 1.29.0 negotiates four legacy versions
through 2025-11-25; 2026-07-28 remains unsupported. There is still no host-launchable
raw transport, real caller authentication or selected provider. SDK interoperability
is useful offline evidence but does not advance native-host or private-roundtrip
acceptance without the corresponding actual tests. See MCP_ADAPTER.md for limits.


The v29 strict raw JSON codec and optional LF bridge close the pre-SDK parsing and
framing gap for caller-supplied async byte endpoints. Actual SDK client tests use
in-memory byte streams, not an installed native host or concrete network transport.
This is bounded offline protocol evidence, not universal conformance. All native,
identity/custody, private-roundtrip and wake gates remain open. In particular, clean
EOF can discard queued replies and cannot prove that admitted work did not execute.
