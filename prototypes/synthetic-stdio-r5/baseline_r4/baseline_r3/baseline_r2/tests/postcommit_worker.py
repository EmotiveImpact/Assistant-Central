"""TEST ONLY: simulate response loss after durable owner-command commit."""
import sys
import time
from independent_peer.endpoint import Endpoint
from independent_peer.worker import main


class PostCommitEndpoint(Endpoint):
    def handle_owner(self, command):
        result = super().handle_owner(command)
        if command.get('op') == 'approve_send':
            time.sleep(60)  # Test kills this child after observing its finite client deadline.
        return result


if __name__ == '__main__':
    sys.exit(main(PostCommitEndpoint))
