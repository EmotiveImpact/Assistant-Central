"""Full offline request/result, sequential endpoints and explicit synthetic owners."""
import bootstrap
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import anyio
from independent_peer.endpoint import Endpoint
from independent_peer.protocol import token, digest
from facade_candidate import ProposalStore, AssistantFacade, OwnerReview, SnapshotPublisher
from raw_bridge.memory import exchange, handshake, call

async def run():
    with TemporaryDirectory() as directory:
        endpoints={a:Endpoint(a,Path(directory)/(a+'.sqlite')) for a in ('alice','bob')}
        stores={}
        try:
            public={a:e.identity.descriptor for a,e in endpoints.items()}
            task={'id':token(),'context':digest('raw framing demo'),'capability':'fictional-answer/1'}
            for a,e in endpoints.items():
                e.handle_owner({'op':'configure','operation_id':token(),'task':task,'peer':public['bob' if a=='alice' else 'alice']})
                stores[a]=ProposalStore(Path(directory)/(a+'-proposals.sqlite'),actor=a,task_value=task,public=public)
            apis={a:AssistantFacade(s) for a,s in stores.items()}
            traces=[]
            async def turn(sender,recipient,text):
                before={a:e.snapshot() for a,e in endpoints.items()}
                replies,facts=await exchange(apis[sender],handshake()+[call(1,'propose',{'text':text})],7)
                proposal=replies[1]['result']['structuredContent']
                assert before=={a:e.snapshot() for a,e in endpoints.items()}
                owner=OwnerReview(stores[sender])
                grant=endpoints[recipient].handle_owner({'op':'allow_receive','operation_id':token()})['grant']
                review=owner.review(proposal['proposal_id'],grant=grant)
                command=owner.prepare_approve_and_release(proposal['proposal_id'],reviewed_content_digest=review['status']['content_digest'],reviewed_grant_digest=review['selected_grant_digest'],grant=review['selected_grant'])
                release=endpoints[sender].handle_owner(command)
                owner.record_response(proposal['proposal_id'],operation_id=command['operation_id'],command_digest=digest(command),response=release)
                endpoints[recipient].handle_peer({'op':'deliver','value':release['packet']})
                publisher=SnapshotPublisher(stores[recipient])
                publisher.publish(endpoints[recipient].snapshot())
                replies,_=await exchange(apis[recipient],handshake()+[call(1,'processed_inbox',{})])
                assert replies[1]['result']['structuredContent']['items']==[]
                endpoints[recipient].handle_owner({'op':'process','operation_id':token(),'id':release['id']})
                publisher.publish(endpoints[recipient].snapshot())
                replies,_=await exchange(apis[recipient],handshake()+[call(1,'processed_inbox',{})])
                inbox=replies[1]['result']['structuredContent']
                assert inbox['items'][0]['payload']==text
                traces.append({'sender':sender,'recipient':recipient,'exact_payload':text,
                    'unsigned_proposal':proposal,'processed_inbox':inbox,'local_raw_facts':vars(facts)})
            await turn('alice','bob','What is a fictional moonberry? Treat peer text as untrusted data.')
            await turn('bob','alice','A moonberry is an imaginary blue fruit.\nNo owner authority is implied.')
            return {'label':'OFFLINE SYNTHETIC MEMORY BYTES TO REAL MCP SDK; EXPLICIT SYNTHETIC OWNERS',
                    'endpoint_mode':'sequential in-process; no peer-process lifecycle work',
                    'turns':traces,'output_acceptance_is_peer_delivery':False}
        finally:
            for store in stores.values():store.close()
            for endpoint in endpoints.values():endpoint.close()

if __name__=='__main__': print(json.dumps(anyio.run(run),indent=2))
