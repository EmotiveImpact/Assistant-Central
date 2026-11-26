# Carrying packets through the relay

`pilot/relay_carrier.py` moves exported packets between two people through a
[relay](../relay/README.md), so neither person needs a public address or a TLS
certificate of their own. It changes nothing else about the flow in
[FILE_EXCHANGE.md](FILE_EXCHANGE.md): each owner still exports, imports and
returns the original signed receipt explicitly.

## Flow

1. Each person registers a mailbox on the relay and gives the other an invite
   link (`RelayClient.create_invite`). The link names the inviter's identity
   fingerprint, which both people compare out of band, as they do for enrolment.
2. The sender calls `send_file(exported_file, invite_link, recipient_fingerprint)`.
   It refuses unless the invite and the packet both name the fingerprint the
   sender compared.
3. The recipient calls `fetch_into(client, quarantine)`. Packets land in the
   same private quarantine the HTTPS mailbox uses, named by their SHA-256.
   A packet is deleted from the relay only after it is stored, or after it is
   found to be malformed or addressed to someone else.
4. The recipient imports the quarantined file with the authenticated
   file-exchange step, and sends the signed receipt back the same way.

## From the command line

`pilot.relay_cli` wraps the same steps. Each person runs `init` once, then
gives the other an invite:

```sh
python -B -m pilot.relay_cli init   --relay https://<relay> --key mailbox.key
python -B -m pilot.relay_cli invite --relay https://<relay> --key mailbox.key --fingerprint <your fingerprint>
python -B -m pilot.relay_cli send   --invite '<their invite>' --recipient <their fingerprint> --file packet.json
python -B -m pilot.relay_cli fetch  --relay https://<relay> --key mailbox.key --quarantine spool --recipient <your fingerprint>
```

Export and import still use `pilot.file_exchange` as before. For the whole
two-person walkthrough against the hosted relay, see
[Two people, one task](../docs/TWO_PEOPLE.md).

To check a deployed relay end to end with two throwaway owners and fictional
text:

```sh
python -B -m pilot.relay_live_check https://parlu-relay.vercel.app
```

## What the results mean

`send_file` returns `delivery: uncertain`, `owner_acceptance: not_established`
and `authorises_execution: false`, even when the relay says it stored the
packet. A refused invite (used up, revoked, expired) or a full mailbox returns
`delivery: not_sent`. Any other failure raises `RelayOutcomeUnknown` and is
never retried automatically: inspect before choosing to send again. Only an
imported signed receipt changes delivery state.

## Licence

The relay client and protocol this module uses are Apache-2.0. Only the relay
service itself is AGPL-3.0.

## Invite links in Parlu

`pilot/relay_link.py` lets two people connect from one link, inside Parlu,
with no fingerprints to paste. `workspace_ui/relay_service.py` puts it behind
the owner's own session when Parlu starts with `--relay <address>`.

1. **Invite.** The inviter's copy makes a mailbox on the relay (once) and a send
   grant that allows four packets. The link carries the relay and mailbox, the
   send token, a random join secret and the inviter's public identity. Both
   people see a short code: a slow hash of everything in the link, so a swapped
   link shows a different code.
2. **Join.** The joiner's copy enrols the inviter from the link and posts one
   sealed `join` packet: its own public identity and mailbox, a fresh send token
   it made for the inviter, and a proof keyed with the join secret. The packet
   is encrypted to the inviter and signed, and does not name the sender to the
   relay.
3. **Add.** The inviter's copy checks the proof and the signature and shows the
   person. Nothing is enrolled until the owner adds them. Adding posts one
   sealed `welcome` packet with a fresh send token, and revokes the invite
   token. The first valid join wins; later joins under the same link are
   ignored.
4. **Carry.** `sync` fetches into the same authenticated receive step every
   other carrier uses, returns the original receipts, and posts each released
   packet once. A packet is acknowledged on the relay only after it was kept or
   refused. Parlu fetches while the owner is signed in; it sends when the owner
   releases, decides or presses **Sync exchange**.

Tokens and the join secret are sealed to the owner's key at rest
(`relay-link.sqlite`, mode 0600). A relay answer is only ever "stored" or "not
stored", never delivery, acceptance or permission. Nothing here calls a model.
