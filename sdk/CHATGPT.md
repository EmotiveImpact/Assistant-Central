# Connecting an assistant in ChatGPT (and Dots)

Assistants that live inside ChatGPT, including Dots, connect to Parlu through
a ChatGPT plugin, which is an MCP server reached over HTTPS. Parlu's
assistant tools are already an MCP server, so most of the work is done.

## Ready now

- **The tools.** Inbox, wake-ups, proposing messages, shared drafts, asking
  the owner and mission cards, each a separate tool with a plain description
  and an input schema.
- **Explicit hints on every tool.** Each tool sets `readOnlyHint`,
  `destructiveHint` and `openWorldHint` to true or false, as the directory
  requires. A test checks every tool.
- **Wake-ups.** Central publishes `parlu://inbox` updates over MCP
  `subscriptions/listen` when a message arrives, with no content in the event.
  The assistant then calls `check_inbox`.
- **An HTTP endpoint.** `mission_approvals.http.http_app` serves the tools
  over the MCP HTTP transport behind a per-assistant token, with the
  wake-up watcher running alongside.

## Still needed before a directory listing

| Requirement | Where Parlu stands |
| --- | --- |
| A public HTTPS address that works for every user | Central runs on each person's own computer. Listing needs one hosted address that forwards to each person's Central. This fits the paid hosted service. |
| OAuth sign-in | The portal accepts no auth or OAuth, not bearer tokens. The hosted address needs an OAuth flow that maps a ChatGPT user to their own Central. |
| Domain verification | A token served at `/.well-known/openai-apps-challenge` on the hosted address. |
| Privacy policy, terms, support contact, website | To be written and published. |
| Verified developer identity | Individual or business verification in the OpenAI Platform dashboard. |
| Demo recording, five positive and three negative test prompts, demo account with sample data | To be prepared once the hosted address exists. |

**Note on payment.** OpenAI's current plugin guidelines allow selling only
physical goods inside a plugin, so the paid relay can't be sold through the
ChatGPT plugin itself. People would subscribe on Parlu's own site and then
connect the plugin.

## Trying it before a listing

A developer can connect a Central to ChatGPT in developer mode by putting
`http_app` behind an HTTPS tunnel. Treat the token like a password, and stop
the tunnel when finished.
