# Two scripted peers, separate owner decisions

This runnable offline demo connects **two fixed scripted child processes** to
immutable actor/task sessions in one disposable owner workspace. It demonstrates
proposals and a bounded-text handoff only. The owner operator still controls
transport bindings, pairing, import, exact review, approval, submission, delivery
and receipt processing through the existing terminal console.

It is not a real provider integration, AI execution, authenticated host, full MCP
implementation, automatic wake, operating-system sandbox or production network.
Distinct PIDs prove distinct local processes, not isolation or interoperability.
No accounts, network, sockets, browser, credentials, provider configuration,
persistent storage or optional continuity are used. Task data is temporary;
quitting discards it. Existing fictional fixture keys remain in trusted owner and
executor processes, not in client configuration or passed descriptors.

## Run interactively (default)

Use the existing offline dependencies described in QUICKSTART.md, then:

```sh
python offline_peer_demo.py
```

1. Copy the exact `task-preview` command printed at startup. Review it, enter
   `task-create`, and separately type `CREATE TASK`. This creates the fixed
   custom-peer task with a 100-character response limit. Creation does not select
   it. Enter `select custom-peer` explicitly.
2. Read `state alice` and `state bob`. Review both transport bindings and use the
   existing `action` bind commands with their exact digests and separate owner
   confirmations, as described in CONSOLE_GUIDE.md. The existing adapter requires
   both bindings before clients can launch. No pairing or sending is implied.
3. Enter `peers-start`. It prints two distinct PIDs and the immutable selected
   route. Start is allowed once only in this demo lifetime. Then enter
   `peer alice discover` and `peer bob discover`. Each lists only `propose`,
   `proposal_status` and `inbox` through the restricted protocol.
4. `peer alice propose` stages the fixed request. It does not create owner
   approval. Use `peer alice status` and `peer bob inbox` for explicit inspection.
   Nothing runs between commands. There is no polling, reconnect or automatic
   mutation retry.
5. Use `next` to inspect each of the two pairing reviews. Approve and submit each
   separately only if the trusted operator chooses it, using the existing exact
   owner commands in CONSOLE_GUIDE.md. Stop after pairing to import the proposal.
6. `import alice peer-alice` opens the candidate for owner review. Read its exact
   review, then separately choose approval, submit and attempt with the existing
   owner controls. After a receipt, `peer bob inbox` is still empty. The owner
   must explicitly process that delivery before Bob can read the request.
7. `peer bob propose` stages this fixed inert result only after the request was
   processed: “The fictional moon garden glows blue.” It is linked to the exact
   request digest. `import bob peer-bob` opens its owner review. Complete the
   separate chosen approval, submission, delivery and processing steps. Alice's
   inbox becomes visible only after processing: `peer alice inbox`.
8. `quit` ends both clients and closes the disposable workspace. A stopped task
   group fences existing client proposal callbacks; read-only history remains
   available. Selecting another task does not rebind either client.

The peer command grammar is closed: `peer <alice|bob>
<discover|propose|status|inbox>`, plus `peers-start` with no arguments. It cannot
accept owner commands, alternate routes, arbitrary executables or client scripts.
Invalid input is refused. The normal `workspace_console.py` behavior is unchanged
unless trusted code explicitly injects its optional command handler.

## Reproduce synthetic evidence

```sh
python offline_peer_demo.py --simulate
python -m unittest discover -s tests -p 'test_offline_peer*.py' -v
```

Simulation is explicitly labeled **SIMULATED OWNER CHOICES**. It performs fixed
synthetic binding and pairing choices, then uses the same proposal import and
owner action APIs as the console. It is not evidence of real human approval. It
does not bypass reviews, change owner logic, grant client authority or continue
through uncertainty. It verifies three discovered tools, two distinct clients,
and empty recipient inboxes before processing in both directions.

A shortened successful transcript (PIDs vary):

```text
SIMULATED OWNER CHOICES: synthetic reproducibility only, not human consent
EXPLICIT SYNTHETIC TASK SELECTION custom-peer <exact context>
SIMULATED OWNER DECISION bind                 [each owner separately]
CLIENT alice discovered propose, proposal_status, inbox
CLIENT bob discovered propose, proposal_status, inbox
PROPOSAL ONLY ... state: awaiting_owner_review
SIMULATED OWNER DECISION approve / submit     [each pairing separately]
OWNER IMPORT unsigned review
SIMULATED OWNER DECISION approve / submit / attempt
DELIVERY RECEIPT present; recipient processed inbox still empty
SIMULATED OWNER DECISION process
PROCESSING bob inbox contains exact request
PROPOSAL ONLY bob fixed result
OWNER IMPORT unsigned review
SIMULATED OWNER DECISION approve / submit / attempt
DELIVERY RECEIPT present; recipient processed inbox still empty
SIMULATED OWNER DECISION process
PROCESSING alice inbox contains exact result
OFFLINE ROUNDTRIP COMPLETE: two scripted clients, separate synthetic owner decisions
Clients reaped; temporary workspace discarded. No live interoperability claimed.
```

## Trust and transport boundaries

`offline_peer_demo.py` is trusted composition. It owns the existing workspace and
creates one exact session per actor. Its optional console handler receives a copy
of the selected route, verifies the frozen fixture selector/context, and never
changes console selection. All owner review logic remains in existing services.

`offline_peer_client.py` imports only Python's json, os and sys modules. It runs
with `python -I`, an empty environment and `close_fds=True`. Only two explicitly
passed anonymous descriptors accompany its ordinary standard streams. The fixed
script receives inert envelope/proposal ID data and closed explicit step commands
on stdin. Its stdout carries only restricted JSON-RPC. One descriptor carries
protocol responses; another carries bounded step reports. It receives no owner
pipes, signing material, workspace objects or executor references. Neither the
control pipe nor diagnostic reports are provider-protocol interoperability
proof. The client can propose only through the existing restricted session; the
protocol separately validates the envelope against its immutable actor/task.

`offline_peer_pipes.py` is a narrow, synchronous supervisor, not an extension of
`fixture_ipc.JsonProcess`. That fixture's signer/executor executable allowlist is
unchanged. The default supervisor launches the fixed Python client script. The explicit
mixed-language option described in OFFLINE_MIXED_PEERS.md selects the one shipped
Node script for a chosen actor; there is no arbitrary configurable executable. It calls the captured restricted session only
for complete bounded LF-delimited frames. The blocking stream helper remains
unchanged; this launcher supplies nonblocking pipe waits instead.

Each explicit step has a three-second pipe-wait deadline, at most eight complete
frames, 16 KiB protocol inputs, 32 KiB protocol outputs and 64 KiB control/report
frames. Short writes continue only the remaining response bytes. EOF, partial
EOF, oversize frames, timeout, malformed/unmatched reports, lost output or extra
buffered report bytes terminate the affected client/session without callback
replay. Reports must match the actual last server response in that step and are
still diagnostic data, never owner authority. A lost reply can follow a committed
proposal. No failure proves nondelivery or permits resend. Preserve owner history
and inspect it through existing controls; the demo does not replace the client.

These deadlines **bound pipe waits**, not process spawning, trusted callback
execution, lock acquisition, Python scheduling or whole owner actions. Existing
fixture IPC separately bounds its process communication. The workspace lock does
not preempt an action already started, and a group stop cannot recall disclosed
data. No background service reads peers while the owner is idle at the prompt;
unexpected peer output remains unprocessed until a requested step. Cleanup closes
all owned descriptors and attempts to reap each child, escalating from EOF to
terminate to kill with bounded waits. A cleanup error is retained and prevents a
clean-discard claim even after later idempotent close calls.

The processes run under the same OS user and can potentially inspect same-user
files or processes. Python import discipline, passed-descriptor restrictions and
fixed scripts are not a hostile-code sandbox. This fixture does not authenticate
real people or providers. Native host acceptance, private network roundtrips,
automatic wake and operational readiness remain unverified, as described in
PROVIDER_READINESS.md.


## Optional independent Node client

v27 adds `--mixed-node alice` or `--mixed-node bob` to explicitly select one fixed
Node implementation. The other client stays Python and the default is unchanged.
Owner actions are the same separate choices. See OFFLINE_MIXED_PEERS.md; this adds
cross-language wire evidence only, not native host/provider acceptance.
