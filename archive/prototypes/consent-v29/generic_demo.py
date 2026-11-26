"""Two fictional provider-labeled assistants exchange a non-meeting task offline.

--simulate explicitly authorizes simulated fixture choices, not real communication.
No URL is visited, task is executed, provider is contacted, or file is shared. The
unchanged pinned A4A crypto modules carry exact signed owner-approved payloads.
"""
import argparse
import json
import tempfile
from pathlib import Path
from generic_capabilities import PUBLIC_SHORTLIST
from generic_protocol import IdentityReference, Conversation, Task, task_envelope
from generic_session import GenericPersistentSession
from durable import LocalDelivery
from integrated_fixture import FixtureAuthorities
from owner_auth import SignedOwnerGateway
from encrypted_delivery import DurableEncryptedOutbox, OfflineReceiver
from network import digest


def fixture():
    # Preserve the original public fixture API and exact payloads.
    from task_fixtures import fixture as catalog_fixture
    return catalog_fixture('garden')


def run():
    task,identities,request,result=fixture();now=[1000];stores=[]
    with tempfile.TemporaryDirectory(prefix='generic-agent-task-') as directory:
        try:
            sender=LocalDelivery(Path(directory)/'sender.sqlite3',clock=lambda:now[0]);stores.append(sender)
            session=GenericPersistentSession(sender,identities,task)
            authorities=FixtureAuthorities(task,now[0])
            gateway=SignedOwnerGateway(session,authorities.owner_roots)
            outbox=DurableEncryptedOutbox(gateway,authorities.registry,authorities.transport_keys)
            receivers={}
            for owner in task.participants:
                store=LocalDelivery(Path(directory)/(owner+'.sqlite3'),clock=lambda:now[0]);stores.append(store)
                receivers[owner]=OfflineReceiver(store,authorities.registry,owner,authorities.transport_keys[owner])
            print('OFFLINE NON-MEETING TASK | SIMULATED OWNER CHOICES')
            print('Provider labels:',', '.join(i.provider for i in identities),'(not live integrations)')
            authorities.pair_all(gateway,now[0])
            print('Bilateral pairing created no message:',sender.db.execute('SELECT COUNT(*) FROM encrypted_outbox').fetchone()[0]==0)
            for envelope in (request,result):
                signed=authorities.delivery(envelope,gateway.contact_versions(envelope['sender'],envelope['recipient']),now[0])
                status=outbox.enqueue(signed,envelope)
                print('Exact owner-approved',envelope['type'],'queued; attempts:',status['attempts'])
                outbox.dispatch(status['delivery_id'],receivers[envelope['recipient']])
                outbox.process_received(status['delivery_id'])
                print('Verified receipt and inert task projection:',session.view().state)
            print('Result linked to exact request:',session.view().result['reply_to']==digest(request))
            print('Envelope has no meeting field:',all('meeting' not in e for e in (request,result)))
            print(json.dumps({'task_state':session.view().state,'receipts':sender.db.execute('SELECT COUNT(*) FROM deliveries').fetchone()[0],
                              'transitions':sender.db.execute('SELECT COUNT(*) FROM transitions').fetchone()[0],'live_provider_calls':0,'executed_tools':0},sort_keys=True))
        finally:
            for store in stores:store.close()
    print('Temporary fixture records and keys discarded. No live interoperability claimed.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulate',action='store_true',required=True)
    parser.parse_args();run()
