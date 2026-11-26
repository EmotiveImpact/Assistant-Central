# Archive

These folders hold earlier proofs of the ideas behind Parlu. They are kept
because they still run, their checks still pass in CI, and they show how the
current design was reached. They are not part of the product, and new work
should go into the main folders instead (`pilot/`, `conversation/`,
`workspace_ui/`, `agent_bridge/`, `mission_approvals/`, `relay/`).

| Folder | What it proved |
| --- | --- |
| `prototypes/consent-v29/` | The first offline model of a network of people's assistants: relationships never grant permission, every disclosure needs its own consent, and a pinned MCP adapter can carry proposals. |
| `prototypes/synthetic-stdio-r5/` | A real stdin/stdout MCP launcher can expose a deliberately tiny tool set (`propose`, `proposal_status`, `processed_inbox`) without changing the frozen code beneath it. |
| `team/` | One person's team of assistants: a nominated lead, dependent and parallel tasks, and artifacts that only count once the lead accepts them. |
| `execution/` | Safe retries. A started task, a dispatched attempt, an original result and an accepted artifact are different things, and an interrupted run is marked uncertain rather than repeated. |
| `integration/` | An accepted team artifact can be mapped exactly onto one proposal for another person, and the recipient's accept or reject is recorded separately. |

The pilot and conversation layers took these lessons and rebuilt them with
real owner accounts, encryption and signed delivery between separate people.

## Running the checks

From the repository root:

```sh
python -m pip install -r archive/prototypes/consent-v29/requirements-mcp-offline.txt
python -B archive/team/run_checks.py
python -B archive/execution/run_checks.py
python -B archive/integration/run_checks.py
python -B archive/prototypes/consent-v29/verify_checkpoint.py --full
```

The archived MCP code pins `mcp==1.29.0`, which is older than the version the
main tools use. Install it in a separate virtual environment.
