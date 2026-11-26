"""Fixed offline child entry point; invoked only by fixture with inherited pipes."""
import argparse
import sys

from .endpoint import Endpoint
from .pipes import serve


def main(endpoint_class=Endpoint):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor', choices=('alice', 'bob'), required=True)
    parser.add_argument('--database', required=True)
    for name in ('owner-read', 'owner-write', 'peer-read', 'peer-write'):
        parser.add_argument('--' + name, type=int, required=True)
    args = parser.parse_args()
    try:
        endpoint = endpoint_class(args.actor, args.database)
        serve(endpoint, args.owner_read, args.owner_write, args.peer_read, args.peer_write)
    except Exception as exc:
        # Deliberately no payload/key dump or traceback in normal service.
        print('Endpoint closed; admission stopped; pending outcomes may be uncertain.', file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
