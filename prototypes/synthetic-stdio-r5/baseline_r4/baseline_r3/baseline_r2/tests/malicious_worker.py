"""TEST ONLY: malicious Bob owns Bob's signing key and bypasses Bob's send policy.

The production worker never imports this module. It models a legitimately bound
peer who can sign arbitrary claims, not an ingress route on an honest endpoint.
"""
import sys
from independent_peer.endpoint import Endpoint
from independent_peer.protocol import exact, seal
from independent_peer.worker import main


class MaliciousEndpoint(Endpoint):
    def handle_owner(self, command):
        if command.get('op') == 'forge':
            exact(command, 'op body')
            return seal(self.identity, self.peer, self.identity.sign('message', command['body']))
        if command.get('op') == 'forge_evidence':
            exact(command, 'op body domain')
            return self.identity.sign(command['domain'], command['body'])
        return super().handle_owner(command)


if __name__ == '__main__':
    sys.exit(main(MaliciousEndpoint))
