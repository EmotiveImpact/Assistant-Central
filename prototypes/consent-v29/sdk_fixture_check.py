"""Run a pinned A4A encrypted scheduling round trip with all socket calls denied."""
import json
from offline_guard import install
install()
from demo import fixture
from network import canonical
from sdk_transport_fixture import PinnedSdkFixture


def main():
    meeting, agents, _ = fixture()
    transport = PinnedSdkFixture(meeting)
    message = agents[1].preview_availability(meeting)
    wrapped = transport.seal(message, 'offline-fixture-delivery', 1794000000)
    wire = wrapped.model_dump()
    assert canonical(message) not in wire['content']
    assert transport.open(wire, 'alice', 'offline-fixture-delivery') == message
    print(json.dumps({'offline_only': True, 'socket_operations': 'denied',
                      'pinned_sdk_encrypted_round_trip': 'passed',
                      'live_relay_tested': False, 'real_owner_identity_tested': False,
                      'private_keys_saved_or_exported': False}))


if __name__ == '__main__':
    main()
