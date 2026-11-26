# Two people, one task, through the relay

This is the shortest path for two people on different machines to pass one
real task between their copies of Parlu, using the hosted relay at
`https://parlu-relay.vercel.app`. Each step is explicit: nothing is sent,
accepted or run unless one of you does it.

You will each need Python 3.12 and a clone of this repository.

```sh
pip install -r pilot/requirements.txt
```

## 0. Check the relay (optional, one minute)

```sh
python -B -m pilot.relay_live_check https://parlu-relay.vercel.app
```

This creates two throwaway owners in a temporary folder, sends one fictional
packet from one to the other through the relay, returns the signed receipt and
checks it lands. It prints four numbered steps and `Relay check passed.`

## 1. Set up and open Parlu with the relay

Each person creates their own owner and opens Parlu. The password is typed
privately, never on the command line. Nobody needs an AI key: your own
assistant does the thinking, and Parlu only carries and records.

```sh
python -B -m pilot.server init --directory ~/parlu --owner <your name> --agent <your assistant>
python -B -m workspace_ui.server serve --directory ~/parlu --relay https://parlu-relay.vercel.app
```

Open the address it prints (normally `http://127.0.0.1:8877`) and sign in.

## 2. Connect with one invite link

1. **The person inviting** (say Edem) goes to **Assistants** and chooses
   **Invite someone**. Parlu shows a link, a QR code and a short code such as
   `UK7J-5N3X`. Send the link to the other person, for example in a message.
   Treat it like a password.
2. **The person joining** (say Maya) opens the link. The relay's page has a
   button that opens it in Parlu on her computer. She can also choose **Join
   with a link** in Parlu and paste it. Parlu shows who the invite is from and
   the same short code.
3. **Both check the code**, for example on a call. If it matches, Maya
   chooses **Join Edem**. If it does not, she stops: someone may have swapped
   the link.
4. **Edem adds Maya.** Within a few seconds a card appears on Edem's Home:
   "Maya and Otto used your invite". He opens it, checks the same code again
   and chooses **Add Maya and Otto**. Maya's copy hears back on its next sync.

Each link is for one person and stops working once someone joins, when it
expires, or when you revoke it under **Assistants**. Joining never agrees to
any work: every proposal still needs its own yes.

The short code is what stops anyone else from slipping in. The relay never
sees the part of the link after `#`, which holds the join secret.

## 3. Send a task and decide on it

From here everything happens in Parlu. Edem drafts a proposal for Maya,
reviews it and releases it, and Parlu posts it to the relay straight away.
Maya's copy fetches it while she is signed in, returns the signed receipt and
shows the proposal for her decision. Her accept or decline goes back the same
way. **Sync exchange** at the foot of the page fetches and sends on demand.

The relay never decides anything. A receipt only says a packet arrived; it
never means the other person accepted it.

## The command line, if you prefer

The earlier path still works for people who want every step by hand: swap
fingerprints over a channel you trust, enrol each other in Parlu, then use
`pilot.relay_cli` to make a mailbox and invite, and `pilot.file_exchange` to
export and import each packet.

```sh
python -B -m pilot.relay_cli init --relay https://parlu-relay.vercel.app --key mailbox.key
python -B -m pilot.relay_cli invite --relay https://parlu-relay.vercel.app --key mailbox.key \
  --fingerprint <your fingerprint>
python -B -m pilot.file_exchange --directory ~/parlu export \
  --message-id <message id from the outbox> --output handoff/task.json
python -B -m pilot.relay_cli send --invite '<their invite>' \
  --recipient <their fingerprint> --file handoff/task.json
python -B -m pilot.relay_cli fetch --relay https://parlu-relay.vercel.app --key mailbox.key \
  --quarantine spool --recipient <your fingerprint>
python -B -m pilot.file_exchange --directory ~/parlu import \
  --input spool/<file printed by fetch> --receipt-output handoff/receipt.json
```

Stop Parlu before using `pilot.file_exchange`, as it takes the same lock.

## Stopping

To stop working with someone, open **Assistants**, choose **Open** on their
assistant and then **Remove**. It asks for a deliberate hold, because it is
final: nothing new from that assistant is accepted, their relay link is
closed, and the same key cannot be added back. Work you already shared stays
in your history.

## If something goes wrong

- "This invite has been used, revoked or has expired": ask for a fresh one.
- "The relay could not be reached": nothing was lost and nothing was sent
  twice. Try **Sync exchange** again in a moment.
- `delivery: not_sent` (command line): the invite is used up, revoked or
  expired, or the mailbox is full. Ask for a fresh invite.
- `Relay outcome unknown`: the packet may or may not be stored. Nothing is
  retried for you. Ask the other person to fetch before you send again.
- The relay keeps packets for at most 14 days and deletes each one once the
  recipient has stored it.

More detail: [invite links](../pilot/RELAY_CARRIER.md#invite-links-in-parlu), [relay carrier](../pilot/RELAY_CARRIER.md),
[file exchange](../pilot/FILE_EXCHANGE.md), [relay](../relay/README.md).
