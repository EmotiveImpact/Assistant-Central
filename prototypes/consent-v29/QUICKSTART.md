# Try the local assistant-network prototype

This is an offline fictional development fixture, not a connected assistant
network. Use invented questions and responses only. Do not enter real personal,
private or account data. Alice and Bob are fictional roles controlled by one
trusted local operator, not authenticated people.

## Run it

1. Extract the checkpoint ZIP and open a terminal in `agent-network-prototype`.
2. Use Python 3.11 or newer and a dedicated virtual environment:

   ```sh
   python -m venv .venv
   # macOS/Linux:
   . .venv/bin/activate
   python -m pip install -r requirements-offline.txt
   python local_owner_app.py --workspace
   ```

   Installing dependencies may use the package registry. The running fixture
   does not require an account, API key, relay, calendar or provider connection.
   Node 18+ is needed for full verification and the optional mixed-language
   demo, not the Python-only app. Node 24.22.1/Linux is the tested runtime.
   The fixture was verified on Linux with Python 3.12. Windows and macOS have
   not been acceptance-tested; some pipe/selector behavior is platform-specific.
3. Open the `LOCAL_OWNER_URL` printed by your own terminal. It is a loopback URL
   for that computer only. Keep the terminal running and do not expose its port.

Actual browser/native-dialog, visual and accessibility acceptance have not been
verified in the development environment. See `UI_VERIFICATION.md` for limits.

## Complete a fictional exchange

1. Choose **Compose temporary task**. Enter a short identifier and fictional
   question, pick the requesting role and capability, then preview it. Use a
   public-resource shortlist with an item count, or a bounded plain-text exchange
   with a reply-character limit.
2. Review the exact context and type `CREATE TASK`. This starts a temporary task
   only; nothing has been bound, paired, approved or sent.
3. Review each role's transport binding separately and type its displayed phrase.
4. Choose **Prepare next review**. Review and approve each pairing direction,
   then separately submit it. Repeat for the question's exact message review.
5. For the approved question, separately submit, start its delivery and process
   the verified receipt. A receipt alone is not a processed message.
6. Switch to the responder. **Received messages** shows the processed question.
   **Compose response** lets the local operator enter fictional resource items or plain text, preview
   the exact reply and open an unsigned review. This does not run an AI agent.
7. Approve that exact response, submit it, start delivery and process its receipt
   using the existing separate controls. Switch to the requester and open
   **Received messages** to read the processed result.

The catalog's garden and astronomy examples can also be explicitly created. Their
**Prepare next review** guide uses fixed fictional messages. Custom tasks do not
invent a response automatically.

## If something stops

- A pending or deferred review grants no authority. Resume deliberately.
- Reviews and pairings expire. Use the explicit replacement or pairing controls
  when offered; they prepare new reviews and do not automatically renew consent.
- Declined or withdrawn history is retained. Repeating the same response opens
  the original review rather than silently creating a new authorization.
- A missing response is an unknown outcome, not proof that nothing happened.
  Inspect the task/inbox or use the existing receipt check. Do not blindly resend.
- **Close only this task** discards that task's temporary processes, keys and
  records when cleanup succeeds. A closed or uncertain slot cannot be recreated
  in the same run. Other tasks remain separate.
- Closing a browser tab does not stop the launcher. Use Ctrl+C in its terminal
  when finished. Stop and inspect its temporary state if cleanup is reported as
  uncertain. This prototype has no persistent inbox or lost-key recovery.

## What this proves, and what it does not

The checkpoint tests local scope, explicit consent, cryptographic fixtures,
receipt/processing distinctions, durable review history and frontend models.
It does not prove real person authentication, native provider compatibility,
automatic host wake, operating-system isolation or production security. Links
and received text are inert, unverified data, never permission to browse or act.
See `PROVIDER_READINESS.md` before planning any real integration.

## Verify an extracted checkpoint offline

From the extracted directory, with your already-prepared dedicated Python 3.11+
virtual environment active:

```sh
python verify_checkpoint.py
python verify_checkpoint.py --full
```

The first command is a fast preflight, not a test-suite pass. It checks the latest
numbered `verification-vN.json`, its source SHA-256 manifest, vendored hashes in
`UPSTREAM.json`, the Python version, importable pinned crypto/MCP dependencies, and
Node 18+. It installs nothing and opens no browser or network connection. Use
`--checkpoint verification-vN.json` to select metadata explicitly; this still
checks the entire extracted source tree, not a historical subset. Run it with
Python from a dedicated environment with `requirements-mcp-offline.txt` when
verifying the complete checkpoint. That optional file includes the base pins and
MCP SDK 1.29.0; it is not needed for the existing Python-only owner application.
The probe uses Python's safe-path option (`-P`) and preserves the selected
environment, including an existing offline `PYTHONPATH` dependency directory.
Only use trusted dependencies. Linux is the tested fixture platform; the portable
verifier does not establish Windows or macOS runtime acceptance. Subprocess pipe
selectors in the fixture can behave differently on Windows.

`--full` additionally runs `python -m unittest discover -s tests -v` and all 15
known Node DOM-model suites. Commands are fixed in the verifier, never read from
metadata. A bad hash blocks all suites. Missing Python dependencies block the
Python suite; missing Node blocks both Python (which includes mixed-client
cases) and DOM-model suites. If Python prerequisites fail but Node is available,
DOM-model suites can still run. Missing tools, wrong dependency versions, failures, timeouts,
and skipped Python tests never produce an overall success. Node is optional for
running the app but required for a complete verification result.

Both commands print a JSON report with `passed`, `failed`, or `not-run` per check
and suite, exact executed argument lists, exit codes, and the last 6 KiB of each
process's output. Exit 0 means the requested mode passed; exit 1 means incomplete
or failed; argparse uses exit 2 for invalid command-line arguments. Preflight
reports every suite as `not-run`. Full-suite output includes the Python test
count and Node suite summaries; historical counts in checkpoint metadata are not
substituted for current results. Prerequisite commands have a 30-second timeout;
each suite has a 10-minute timeout. Temporary logs are removed after reading.
Tests may create their normal disposable local fixture state. A timed-out parent
process cannot guarantee teardown of every descendant on every platform.

Checksums detect inconsistency, not malicious replacement of both source and
manifest. Use a trusted checkpoint. Source freezes cover root Python and JavaScript (.js/.cjs) files,
Python/JS tests, both UI trees and local vendor package wrappers; upstream
vendored Python sources are checked separately.
The JSON metadata and hash list must not hash themselves. New Python sources,
including this verifier and its tests, must be included when producing a new
freeze. Documentation, historical logs and environment configuration are not
source-authentication evidence. No result establishes real-browser, visual,
accessibility, live-provider, real-person identity or OS-isolation acceptance.

## Group related tasks and stop local work

Choose **Fictional task groups**. Select exact task contexts, enter a fictional
group ID and label, preview the membership and type `CREATE GROUP`. Nothing is
bound, paired, approved or sent. Attaching another existing task requires its
own preview and `ATTACH TASK`; labels never attach tasks automatically.

To stop future work in all linked contexts, inspect the group, choose
**Review stop further group work**, review every member and type `STOP GROUP`.
This stop is permanent for the launcher run, including through overlapping
groups. It is local and serialized: already-entered work may finish first, and
disclosed content cannot be recalled. It does not block a person across other
tasks, send remote notices or establish cancellation/nondelivery evidence.

Stopped tasks still let you read processed messages and proposal/review history,
check existing receipts, inspect committed status, reduce unused authority and
close the task. New approvals, imports, submissions, delivery attempts and
processing are blocked. There is no resume. A missing group-action response is
uncertain: inspect that exact group without automatically repeating it.

## Optional trusted terminal interface

Use `python workspace_console.py` from the same prepared environment. Type
`help`, then follow CONSOLE_GUIDE.md for custom task, response, group and history
commands. Task/group commits display their frozen review and ask a separate exact
confirmation. The existing `--simulate` mode is explicitly simulated fictional
owner choices; it is not a live assistant integration or real owner consent.

If communication becomes uncertain, the console preserves read-only inspection
until an explicit close/quit. No mutation is automatically retried. Reads from a
terminated child may still fail. Inspect whatever evidence remains before
choosing cleanup; this fixture does not offer persistent or lost-key recovery.

## Optional fictional continuity

Restarting discards the current disposable workspace, so finish inspecting it
before choosing a new launch. To create a new explicitly opted-in run, use:

```sh
python local_owner_app.py --workspace --continuity
# Or the trusted console:
python workspace_console.py --continuity
```

Choose **Fictional continuity proofs**. Enrollment and each association require
separate previews and the full displayed digest confirmation. An association
selects an existing task, its exact context and an actual fictional owner. It
starts no task, grants no authority and sends no message. Independent task keys
remain independent. Labels and task groups never infer associations.

Association reviews expire after two minutes. A successful historical certificate
can be locally recognized for up to 24 hours, subject to task/identity fences.
Retirement removes recognition but does not cancel tasks, revoke grants or stop
messages. Failed or lost responses remain uncertain; inspect state without
repeating signing or automatically enrolling a replacement. Nothing persists
across workspace exit. Read CONTINUITY_OWNER_GUIDE.md before trying the fixture.

## Optional two-client terminal walkthrough

`python offline_peer_demo.py` offers two fixed scripted client processes without
opening a browser or network connection. Follow OFFLINE_PEER_DEMO.md: create and
select the fixed task, review both bindings, then explicitly start and step each
client. Clients can propose or inspect, but cannot approve, send or process.
The trusted operator still makes each owner decision separately.

Use `python offline_peer_demo.py --simulate` only to reproduce visibly labeled
synthetic owner choices. This is not evidence of human approval or provider
interoperability. It creates no continuity identity or persistent configuration.


To explicitly select one Node client in that same walkthrough, add
`--mixed-node alice` or `--mixed-node bob`; use `--simulate` only for labeled
synthetic owner choices. Nothing installs or connects a provider. Read
OFFLINE_MIXED_PEERS.md for runtime, Unicode and negotiation evidence. The launcher
uses only the shipped fixed scripts, never an arbitrary executable argument.


## Optional MCP protocol adapter

The SDK adapter is a library factory, not a launchable host plugin. Read
MCP_ADAPTER.md for the trusted binding contract and offline supported versions.
It opens no listener and chooses no host identity or peer transport. To prepare a
dedicated environment for its tests, the optional requirements-mcp-offline.txt
lists the reviewed MCP SDK and base dependencies. Dependency installation may
contact the package registry; the verifier itself never installs anything.
Missing/mismatched MCP causes incomplete preflight and a not-run Python suite,
not a silently skipped success. Base owner UI/console remain independent of MCP.

The optional MCP_RAW_CODEC.md library adds strict bounded raw JSON and LF framing
for caller-owned async byte streams, not a native host entry point. It opens no
connection. Read its EOF/uncertain-outcome and embedding responsibilities before
composition. The original restricted scripted-client walkthrough is unchanged.
