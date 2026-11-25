# Assistant Central relay

The relay is a small hosted service that carries packets between people's
assistants when they are not on the same network. It stores each packet briefly
until the recipient collects it, then forgets it.

**Licence: AGPL-3.0-only** for the relay service (see [LICENSE](LICENSE)). The
client side, `acrelay/client.py` and `acrelay/protocol.py`, is Apache-2.0 like
the rest of Assistant Central, so any app can talk to a relay without taking on
the AGPL. If you run a modified relay for other people, you must offer them its
source; the relay's `/source` route points to it.

## What the relay can and cannot see

| The relay sees | The relay never sees |
| --- | --- |
| A random mailbox id and its public key | Who owns the mailbox |
| Hashed send tokens | The tokens themselves, or invite links |
| Opaque, already encrypted packets, kept for at most 14 days | Any message, draft or file in readable form |
| Which send grant a packet arrived under | Who the sender is |

Packets are end to end encrypted and signed by the owners' own assistants
before they reach the relay. The relay cannot read, change or forge them
without the recipient noticing.

## How people connect

1. Each owner's Central creates a dedicated **mailbox key** (separate from
   their identity key) and registers a mailbox. Every owner request is signed
   with that key, carries a timestamp and a one-time nonce, and cannot be
   replayed.
2. To invite someone, the owner creates a **send grant** (a random token, a
   number of packets and an expiry) and shares an **invite link**:
   `https://relay.example/invite#...`. Everything after `#` stays in the
   browser and is never sent to any server. It holds the relay address, the
   mailbox, the send token and the inviter's identity fingerprint, which the
   invitee compares with the inviter by another channel.
3. The invitee's Central sends an introduction packet with that token, and can
   include its own invite back. After that, each side holds a grant for the
   other.
4. An owner can revoke any grant at any time. Unknown, used up, expired and
   revoked tokens all get the same refusal.

## Limits

64 KiB per packet, 1,000 packets or 32 MiB waiting per mailbox, 14 days'
retention, 256 grants per mailbox, grants of at most a year and 100,000
packets. Clock skew of five minutes is allowed for signed requests.

## API

| Method and path | Who | What |
| --- | --- | --- |
| `POST /v1/mailboxes` | owner, self-signed | Register a mailbox (idempotent) |
| `POST /v1/mailboxes/{id}/grants` | owner, signed | Create a send grant from a token hash |
| `DELETE /v1/mailboxes/{id}/grants/{grant}` | owner, signed | Revoke a grant |
| `POST /v1/mailboxes/{id}/packets` | sender, `Bearer` token | Deliver one opaque packet |
| `GET /v1/mailboxes/{id}/packets?after=&limit=` | owner, signed | Collect waiting packets |
| `DELETE /v1/mailboxes/{id}/packets?through=` | owner, signed | Delete collected packets |
| `GET /v1/health`, `GET /source`, `GET /invite` | anyone | Status, source link, invite landing page |

## Running it

On your own machine (SQLite):

```sh
pip install -r relay/requirements-local.txt
cd relay && python -m acrelay.local --db relay.sqlite
```

On Vercel: deploy the `relay/` folder as its own project and set
`DATABASE_URL` to a Postgres connection string (for example Vercel Postgres or
Neon). `api/index.py` is the function and `vercel.json` routes every path to
it. The Postgres path uses the same SQL as SQLite, but has **not yet been run
against a live Postgres database**; do that before relying on it.

## Tests

```sh
cd relay && python -B -m unittest discover -s tests -t . -v
```

The tests run a real local HTTP server and cover invites, grants, expiry,
revocation, replay and stale signatures, forged mailbox claims, retention,
size limits and restart.
