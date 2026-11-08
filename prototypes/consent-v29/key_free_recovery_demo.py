"""Two-process recovery proof: generated private keys die with preparation process.

Only public fixture bindings and durable records cross into the recovery process.
This recovers evidence of an already-received message, not any identity or key.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def stage(phase,directory):
    from offline_guard import install
    install()
    from demo import fixture
    from durable import LocalDelivery
    from session import PersistentSession
    from owner_auth import SignedOwnerGateway
    from bound_identity import IdentityRegistry
    from encrypted_delivery import DurableEncryptedOutbox, OfflineReceiver, ReceiptReader
    meeting,agents,_=fixture()
    directory=Path(directory)
    sender=LocalDelivery(directory/'sender.sqlite3',clock=lambda:1000)
    receiver_store=LocalDelivery(directory/'receiver.sqlite3',clock=lambda:1000)
    try:
        session=PersistentSession(sender,agents,meeting)
        if phase=='prepare':
            from integrated_fixture import FixtureAuthorities
            authorities=FixtureAuthorities(meeting,1000)
            registry=authorities.registry
            gateway=SignedOwnerGateway(session,authorities.owner_roots)
            authorities.pair_all(gateway,1000)
            box=DurableEncryptedOutbox(gateway,registry,authorities.transport_keys)
            receiver=OfflineReceiver(receiver_store,registry,'alice',authorities.transport_keys['alice'])
            message=agents[1].preview_availability(meeting)
            signed=authorities.delivery(message,gateway.contact_versions('bob','alice'),1000)
            nonce=signed['decision']['nonce'];box.enqueue(signed,message)
            class LostAck:
                owner='alice'
                def __init__(self):self.registry=registry
                def receipt(self,identifier):return receiver.receipt(identifier)
                def receive(self,packet):
                    receiver.receive(packet)
                    raise ConnectionError('synthetic lost acknowledgement')
            try:box.dispatch(nonce,LostAck())
            except ConnectionError:pass
            public={'owner_roots':authorities.owner_roots,'bindings':authorities.bindings,'delivery_id':nonce}
            (directory/'public-fixture.json').write_text(json.dumps(public))
            print(json.dumps({'phase':'prepare','sender_state':box.status(nonce)['state'],
                              'private_keys_written':False,'receiver_committed':receiver.receipt(nonce) is not None}))
        else:
            public=json.loads((directory/'public-fixture.json').read_text())
            registry=IdentityRegistry(meeting,public['owner_roots'],public['bindings'])
            gateway=SignedOwnerGateway(session,public['owner_roots'])
            box=DurableEncryptedOutbox(gateway,registry)  # No private transport/owner keys supplied.
            reader=ReceiptReader(receiver_store,registry,'alice')
            nonce=public['delivery_id']
            box.reconcile(nonce,reader)
            status=box.process_received(nonce)
            assert status['state']=='processed' and len(session.view().audit)==1
            print(json.dumps({'phase':'recover','state':status['state'],'attempts':status['attempts'],
                              'private_keys_loaded':False,'new_delivery_possible':False,
                              'scope':'existing signed receipt only; identity recovery not implemented'}))
    finally:sender.close();receiver_store.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=('prepare','recover'))
    parser.add_argument('--fixture-directory')
    args=parser.parse_args()
    if args.phase:
        if not args.fixture_directory:raise ValueError('Internal fixture directory required')
        stage(args.phase,args.fixture_directory)
        return
    with tempfile.TemporaryDirectory(prefix='key-free-network-recovery-') as directory:
        for phase in ('prepare','recover'):
            result=subprocess.run([sys.executable,__file__,'--phase',phase,'--fixture-directory',directory],
                                  text=True,capture_output=True,timeout=10,check=True)
            print(result.stdout.strip())
        print('Preparation process exited before recovery. No generated private keys were persisted.')


if __name__=='__main__':main()
