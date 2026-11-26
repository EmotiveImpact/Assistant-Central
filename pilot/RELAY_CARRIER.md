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

Export and import still use `pilot.file_exchange` as before.

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
