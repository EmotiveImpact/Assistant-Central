"""Offline execution worker: stdio only, public verification keys, no signing keys.

The first frame is trusted local-supervisor bootstrap. All later execution frames
need signed owner decisions. This is not a listening service or owner enrollment UI.
"""
import argparse
import json
import sys
from offline_guard import install
install()
from demo import fixture
from durable import LocalDelivery
from network import Denied
from owner_auth import SignedOwnerGateway
from session import PersistentSession

MAX_FRAME = 16384


def read_frame():
    line = sys.stdin.buffer.readline(MAX_FRAME + 1)
    if not line:
        return None
    if len(line) > MAX_FRAME or not line.endswith(b'\n'):
        raise Denied('Frame exceeds the offline fixture limit')
    return json.loads(line)


def reply(value):
    print(json.dumps(value, sort_keys=True, allow_nan=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-file', required=True)
    parser.add_argument('--fixture', action='store_true', required=True)
    args = parser.parse_args()
    bootstrap = read_frame()
    if type(bootstrap) is not dict or set(bootstrap) != {'owner_public_keys'}:
        raise Denied('Trusted supervisor must supply owner verification roots once')
    store = LocalDelivery(args.state_file)
    try:
        meeting, agents, _ = fixture()
        session = PersistentSession(store, agents, meeting)
        gateway = SignedOwnerGateway(session, bootstrap['owner_public_keys'])
        reply({'ready': True, 'context': session.context, 'fixture_only': True})
        while True:
            try:
                request = read_frame()
            except (ValueError, Denied) as exc:
                reply({'ok': False, 'error': str(exc)})
                return
            if request is None:
                return
            try:
                if type(request) is not dict or set(request) != {'signed', 'envelope'}:
                    raise Denied('Worker accepts only signed decisions, not approval or signing commands')
                result = gateway.apply(request['signed'], request['envelope'])
                reply({'ok': True, **result})
            except (Denied, ValueError, TypeError) as exc:
                reply({'ok': False, 'error': str(exc)})
    finally:
        store.close()


if __name__ == '__main__':
    try:
        main()
    except (Denied, ValueError, EOFError) as exc:
        reply({'ok': False, 'error': str(exc)})
        sys.exit(1)
