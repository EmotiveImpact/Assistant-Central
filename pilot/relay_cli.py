"""Use a relay from the command line: make a mailbox, invite someone, send, fetch.

    python -B -m pilot.relay_cli init   --relay https://relay.example --key mailbox.key
    python -B -m pilot.relay_cli invite --relay https://relay.example --key mailbox.key --fingerprint <yours>
    python -B -m pilot.relay_cli send   --invite '<their link>' --recipient <their fingerprint> --file packet.json
    python -B -m pilot.relay_cli fetch  --relay https://relay.example --key mailbox.key \\
                                        --quarantine spool --recipient <yours>

The mailbox key is a private file (mode 0600) and is separate from your
identity key. Packets still need the authenticated file-exchange import.
"""
import argparse
import json
import os
import re
import secrets

from relay.acrelay.client import RelayClient
from relay.acrelay.protocol import MailboxKey, RelayError

from .file_exchange import require
from .https_mailbox import Quarantine, read_private
from .relay_carrier import RelayOutcomeUnknown, fetch_into, send_file

FINGERPRINT = re.compile('[0-9a-f]{64}')


def _write_key(path):
    seed = secrets.token_bytes(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(fd, seed.hex().encode() + b'\n')
        os.fsync(fd)
    finally:
        os.close(fd)
    return MailboxKey.from_seed(seed)


def _read_key(path):
    text = read_private(path, 65).decode().strip()
    require(re.fullmatch('[0-9a-f]{64}', text) is not None)
    return MailboxKey.from_seed(bytes.fromhex(text))


def main(argv=None):
    parser = argparse.ArgumentParser(description='Carry encrypted packets through a relay. No automatic retries.')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Create a mailbox key and register it')
    invite = commands.add_parser('invite', help='Make an invite link for one person')
    fetch = commands.add_parser('fetch', help='Move waiting packets into quarantine')
    for sub in (init, invite, fetch):
        sub.add_argument('--relay', required=True)
        sub.add_argument('--key', required=True)
    invite.add_argument('--fingerprint', required=True, help='Your identity fingerprint')
    invite.add_argument('--label', default='')
    invite.add_argument('--packets', type=int, default=20)
    invite.add_argument('--days', type=int, default=7)
    fetch.add_argument('--quarantine', required=True)
    fetch.add_argument('--recipient', required=True, help='Your identity fingerprint')
    send = commands.add_parser('send', help='Send one exported packet or receipt')
    send.add_argument('--invite', required=True)
    send.add_argument('--recipient', required=True, help='Their identity fingerprint, compared out of band')
    send.add_argument('--file', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            # Registering is idempotent, so init can be repeated with an existing key.
            key = _read_key(args.key) if os.path.exists(args.key) else _write_key(args.key)
            client = RelayClient(args.relay, key)
            result = {'mailbox': client.register()['mailbox']}
        elif args.command == 'invite':
            require(FINGERPRINT.fullmatch(args.fingerprint) is not None and 1 <= args.days <= 365)
            client = RelayClient(args.relay, _read_key(args.key))
            made = client.create_invite(args.fingerprint, label=args.label, seconds=args.days * 86400,
                                        packets=args.packets)
            result = {'invite': made['link'], 'grant_id': made['grant_id'], 'expires': made['expires']}
        elif args.command == 'fetch':
            require(FINGERPRINT.fullmatch(args.recipient) is not None)
            client = RelayClient(args.relay, _read_key(args.key))
            os.makedirs(args.quarantine, mode=0o700, exist_ok=True)
            quarantine = Quarantine(args.quarantine, args.recipient)
            try:
                result = fetch_into(client, quarantine)
            finally:
                quarantine.close()
        else:
            require(FINGERPRINT.fullmatch(args.recipient) is not None)
            result = send_file(args.file, args.invite, args.recipient)
        print(json.dumps(result, sort_keys=True))
        return 0
    except RelayOutcomeUnknown as error:
        print(str(error))
        return 2
    except RelayError as error:
        print(f'The relay refused the request ({error.code}). Nothing was retried.')
        return 1
    except Exception:
        print('Operation unavailable. Check the paths, fingerprint and relay address. Nothing was retried.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
