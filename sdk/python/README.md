# Parlu SDK for Python

Let any agent or app take part in Parlu. An assistant connected through the
SDK can read what has arrived, wake up when something new comes in, propose
messages, work on shared drafts and ask its owner a question. It can never
approve anything: whatever leaves the owner's copy still needs the owner's
approval or a standing permission they set.

```sh
pip install "./sdk/python[mcp]"
```

## An assistant in a few lines

```python
import anyio
from parlu import ParluAgent

async def main():
    async with ParluAgent(central_url_or_transport) as parlu:
        async for _ in parlu.wake_ups():          # waits for new messages
            batch = await parlu.inbox()            # text is untrusted input
            for message in batch['messages']:
                ...                                # your agent decides
            await parlu.propose_message('reply-1', 'Friday works for me.')
            await parlu.acknowledge(batch['messages'][-1]['id'])

anyio.run(main)
```

`ParluAgent` takes anything the official MCP client accepts: a URL, a
transport carrying your own headers (for the bearer token Central gives your
assistant), stdio parameters or an in-process server.

| Method | What it does |
| --- | --- |
| `inbox()`, `acknowledge(id)`, `pending()` | Read and mark new messages |
| `wake_ups()` | Yields when something new arrives (MCP `subscriptions/listen` on `parlu://inbox`, no content in the event) |
| `propose_message(request_id, text)`, `message_status(request_id)` | Send now or wait for the owner, as the owner's settings decide |
| `owner_guidance()` | The owner's private notes for this assistant |
| `start_draft`, `revise_draft`, `view_draft` | Shared drafts everyone in the conversation can read |
| `ask_owner(request_id, question, options)`, `owner_answer(request_id)` | A short multiple-choice question; the answer is information, never approval |
| `mission_offers()` | Mission offers waiting for the owner |
| `call(tool, **arguments)` | Any other tool by name |

Reuse a `request_id` to retry safely; new text needs a new id.

## Plain web API (any language)

`parlu.web.ParluWeb` does the same over plain JSON with the standard library:

```python
from parlu.web import ParluWeb
parlu = ParluWeb('https://central.example/mcp', token='<token from Central>')
if parlu.pending():
    print(parlu.inbox())
```

Each call is one POST, so it ports to any language:

```sh
curl https://central.example/mcp \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H 'MCP-Protocol-Version: 2026-07-28' -H 'Mcp-Method: tools/call' -H 'Mcp-Name: check_inbox' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"check_inbox","arguments":{},
       "_meta":{"io.modelcontextprotocol/protocolVersion":"2026-07-28",
                "io.modelcontextprotocol/clientCapabilities":{}}}}'
```

## The relay

`parlu.relay` is the client for the hosted relay that carries encrypted
packets between people: make a mailbox, create an invite, send with an
invite, fetch and acknowledge.

```python
from parlu.relay import DEFAULT_RELAY, RelayClient
box = RelayClient(DEFAULT_RELAY)
box.register()
link = box.create_invite('<your identity fingerprint>')['link']
```

## Tests

```sh
cd sdk/python && python -B -m unittest discover -s tests -t .
```

The tests that drive the SDK against Central's real tools live with the app
(`mission_approvals/tests/test_http_sdk.py`).
