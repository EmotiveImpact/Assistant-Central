"""Two disposable copies of Parlu and one local relay, for the invite link browser test.

Fictional owners only. The password below is public fixture data; never use it for
a real owner. Nothing here reaches the internet or calls a model.
"""
import argparse
import json
from pathlib import Path
import tempfile
import threading

from pilot.auth import LocalOwnerAuth
from relay.acrelay.local import serve
from relay.acrelay.service import Relay
from relay.acrelay.store import SqlStore
from .demo import PASSWORD
from .server import WorkspaceHTTPServer


def make_owner(root, owner, agent):
    directory = Path(root) / owner
    auth = LocalOwnerAuth(directory)
    try:
        auth.bootstrap(owner, agent, PASSWORD)
    finally:
        auth.close()
    return directory


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--relay-port', type=int, default=8790)
    parser.add_argument('--edem-port', type=int, default=8791)
    parser.add_argument('--maya-port', type=int, default=8792)
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix='parlu-invite-fixture-') as root:
        store = SqlStore.sqlite(str(Path(root) / 'relay.sqlite'))
        relay = serve(Relay(store), port=args.relay_port)
        relay_url = f'http://127.0.0.1:{relay.server_port}'
        servers = [WorkspaceHTTPServer(make_owner(root, 'edem', 'Juniper'), args.edem_port, relay_url=relay_url),
                   WorkspaceHTTPServer(make_owner(root, 'maya', 'Otto'), args.maya_port, relay_url=relay_url)]
        threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (relay, *servers)]
        for thread in threads:
            thread.start()
        print(json.dumps({'relay': relay_url, 'edem': servers[0].origin, 'maya': servers[1].origin,
                          'password': PASSWORD, 'synthetic_fixture': True}), flush=True)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            for server in (relay, *servers):
                server.shutdown()
                server.server_close()
            store.close()


if __name__ == '__main__':
    main()
