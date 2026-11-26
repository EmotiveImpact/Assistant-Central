# Hosted demo

`hosted/index.py` puts the real Parlu web app online as a public demo on
Vercel, with the same fictional workspace as `python -m workspace_ui.demo`
(Blair and the assistants Atlas, Mira and Orbit). The demo password is shown
on the sign-in card.

- Each warm instance seeds the workspace in its temporary folder, starts the
  unchanged owner server on a private loopback port and passes requests to it.
  Sign-in, sessions, exact review and the security headers are the app's own.
- It holds no real person's keys or records, and starts fresh whenever Vercel
  recycles the instance. Everyone who opens it shares the same fictional Blair.
- `PARLU_RELAY_URL` (optional) turns on invite links through that relay.
- Loopback peer mailboxes (`/peer/...`) are refused here.

The Vercel project uses the repository root, so the root `vercel.json` belongs
to this demo. The relay is a separate project rooted at `relay/`.

Check it locally:

```sh
PARLU_DEMO_SCHEME=http python -B -c "import sys; sys.path.insert(0, '.'); \
from http.server import ThreadingHTTPServer; from hosted.index import handler; \
ThreadingHTTPServer(('127.0.0.1', 8899), handler).serve_forever()"
```

Then open http://127.0.0.1:8899.
