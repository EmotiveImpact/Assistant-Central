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

## 1. Set up and swap fingerprints

Each person creates their own owner and opens Central. The password is typed
privately, never on the command line.

```sh
python -B -m pilot.server init --directory ~/parlu --owner <your name> --agent <your assistant>
python -B -m workspace_ui.server serve --directory ~/parlu
```

Each copy has an identity fingerprint: 64 characters shown in Central. Read
your fingerprints to each other over a channel you trust, such as a call, and enrol the other person as a peer in Central.

Comparing fingerprints this way is what stops anyone else from slipping in.
The relay never sees them.

## 2. Make a mailbox and swap invites

Each person makes a relay mailbox once. The key file is private (mode 0600)
and separate from your identity key.

```sh
python -B -m pilot.relay_cli init --relay https://parlu-relay.vercel.app --key mailbox.key
python -B -m pilot.relay_cli invite --relay https://parlu-relay.vercel.app --key mailbox.key \
  --fingerprint <your fingerprint>
```

`invite` prints a link. Send it to the other person. The secret part of the
link sits after the `#`, so treat the whole link like a password. By default
it allows 20 packets over 7 days.

## 3. Send the task

The person asking (say Alice) drafts the task in Central, reviews it and
releases it, then exports the encrypted packet. Stop Central first, as the
command line takes the same lock:

```sh
mkdir -m 700 handoff
python -B -m pilot.file_exchange --directory ~/parlu export \
  --message-id <message id from the outbox> --output handoff/task.json
python -B -m pilot.relay_cli send --invite '<bob's invite>' \
  --recipient <bob's fingerprint> --file handoff/task.json
```

`send` refuses if the invite or the packet names anyone other than the
fingerprint Alice compared.

## 4. Receive and reply

Bob fetches, imports and returns the signed receipt:

```sh
mkdir -m 700 handoff
python -B -m pilot.relay_cli fetch --relay https://parlu-relay.vercel.app --key mailbox.key \
  --quarantine spool --recipient <bob's fingerprint>
python -B -m pilot.file_exchange --directory ~/parlu import \
  --input spool/<file printed by fetch> --receipt-output handoff/receipt.json
python -B -m pilot.relay_cli send --invite '<alice's invite>' \
  --recipient <alice's fingerprint> --file handoff/receipt.json
```

Bob then opens Central to read the task and decide on it. The receipt only
says the packet arrived; it never means Bob accepted it.

Alice fetches and imports the receipt the same way, and her copy shows the
task as delivered. Bob's answer and any results come back by the same export,
send, fetch and import steps.

## If something goes wrong

- `delivery: not_sent`: the invite is used up, revoked or expired, or the
  mailbox is full. Ask for a fresh invite.
- `Relay outcome unknown`: the packet may or may not be stored. Nothing is
  retried for you. Ask the other person to fetch before you send again.
- The relay keeps packets for at most 14 days and deletes each one once the
  recipient has stored it.

More detail: [relay carrier](../pilot/RELAY_CARRIER.md),
[file exchange](../pilot/FILE_EXCHANGE.md), [relay](../relay/README.md).
