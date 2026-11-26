"""Ordinary sequential synthetic-owner demo, no lifecycle/concurrency probe."""
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import anyio
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'baseline_r2'))
from independent_peer.fixture import Experiment
from independent_peer.protocol import digest
from facade_candidate import ProposalStore, AssistantFacade, OwnerReview, SnapshotPublisher
from mcp_bridge.local import client

async def run():
    with TemporaryDirectory() as directory, Experiment() as experiment:
        peers={'alice':experiment.alice,'bob':experiment.bob}
        public={a:p.owner('describe')['descriptor'] for a,p in peers.items()}
        stores={a:ProposalStore(Path(directory)/(a+'-proposals.sqlite'),actor=a,task_value=experiment.task,public=public) for a in peers}
        try:
            apis={a:AssistantFacade(s) for a,s in stores.items()}
            owner=OwnerReview(stores['alice']);publisher=SnapshotPublisher(stores['bob'])
            grant=peers['bob'].owner('allow_receive')['grant']
            result_grant=peers['alice'].owner('allow_receive')['grant']
            before={a:p.owner('inspect') for a,p in peers.items()}
            async with client(apis['alice']) as (session,init):
                proposal=(await session.call_tool('propose',{'text':'A moonberry is fictional. Treat peer text as untrusted data.'})).structuredContent
                assert before=={a:p.owner('inspect') for a,p in peers.items()}
                # These are explicit trusted synthetic-owner steps, not MCP callbacks.
                review=owner.review(proposal['proposal_id'],grant=grant)
                command=owner.prepare_approve_and_release(proposal['proposal_id'],reviewed_content_digest=review['status']['content_digest'],reviewed_grant_digest=review['selected_grant_digest'],grant=review['selected_grant'])
                released=peers['alice'].owner(command['op'],**{k:v for k,v in command.items() if k!='op'})
                owner.record_response(proposal['proposal_id'],operation_id=command['operation_id'],command_digest=digest(command),response=released)
                status=(await session.call_tool('proposal_status',{'proposal_id':proposal['proposal_id']})).structuredContent
            peers['bob'].peer('deliver',released['packet'])
            publisher.publish(peers['bob'].owner('inspect'))
            async with client(apis['bob']) as (session,_):
                before_processing=(await session.call_tool('processed_inbox',{})).structuredContent
                assert before_processing['items']==[]
                peers['bob'].owner('process',id=released['id'])
                publisher.publish(peers['bob'].owner('inspect'))
                processed=(await session.call_tool('processed_inbox',{})).structuredContent
                result_proposal=(await session.call_tool('propose',{'text':'A moonberry is an imaginary blue fruit.'})).structuredContent
                result_owner=OwnerReview(stores['bob'])
                review=result_owner.review(result_proposal['proposal_id'],grant=result_grant)
                command=result_owner.prepare_approve_and_release(result_proposal['proposal_id'],reviewed_content_digest=review['status']['content_digest'],reviewed_grant_digest=review['selected_grant_digest'],grant=review['selected_grant'])
                result_release=peers['bob'].owner(command['op'],**{k:v for k,v in command.items() if k!='op'})
                result_owner.record_response(result_proposal['proposal_id'],operation_id=command['operation_id'],command_digest=digest(command),response=result_release)
                result_status=(await session.call_tool('proposal_status',{'proposal_id':result_proposal['proposal_id']})).structuredContent
            peers['alice'].peer('deliver',result_release['packet'])
            alice_publisher=SnapshotPublisher(stores['alice'])
            alice_publisher.publish(peers['alice'].owner('inspect'))
            async with client(apis['alice']) as (session,_):
                assert (await session.call_tool('processed_inbox',{})).structuredContent['items']==[]
                peers['alice'].owner('process',id=result_release['id'])
                alice_publisher.publish(peers['alice'].owner('inspect'))
                alice_processed=(await session.call_tool('processed_inbox',{})).structuredContent
                assert alice_processed['items'][0]['payload']=='A moonberry is an imaginary blue fruit.'
            return {'label':'OFFLINE SYNTHETIC MCP TOOLS ONLY; NO HOST AUTHENTICATION',
                    'negotiated_legacy_protocol':init.protocolVersion,'four_separate_stores':True,
                    'proposal_endpoint_state_unchanged':True,'status':status,
                    'before_processing':before_processing,'bob_processed_inbox':processed,
                    'result_status':result_status,'alice_processed_inbox':alice_processed,
                    'excluded_lifecycle_audit':'Not performed or cleared.'}
        finally:
            for store in stores.values():store.close()

if __name__=='__main__':print(json.dumps(anyio.run(run),indent=2))
