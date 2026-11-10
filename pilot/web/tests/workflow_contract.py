"""Validate workflow frontend contracts using actual opt-in HTTP processes.

Only fictional text and fresh owner vaults are used. No secrets are exported to
Node, files or evidence. This is schema evidence, not a browser rendering test.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from pilot.demo import provision, running_process, request
from pilot.crypto import fingerprint
from pilot.workflow import FIXTURE_GRANT


def run():
    records=[]
    with tempfile.TemporaryDirectory(prefix='pilot-workflow-ui-contract-') as directory:
        first,second=Path(directory)/'first',Path(directory)/'second'
        password_a,public_a=provision(first,'fictional-a','atlas')
        password_b,public_b=provision(second,'fictional-b','beacon')
        with running_process(first,synthetic_workflow=True) as (a_url,_),running_process(second,synthetic_workflow=True) as (b_url,_):
            a=request(a_url,'POST','/api/session',{'password':password_a})['token']
            b=request(b_url,'POST','/api/session',{'password':password_b})['token']
            for url,token,peer_url,public in ((a_url,a,b_url,public_b),(b_url,b,a_url,public_a)):
                request(url,'POST','/api/peers',{'public_identity':public,'expected_fingerprint':fingerprint(public),'endpoint':peer_url},token)
            task=request(a_url,'POST','/api/proposals',{'peer_id':fingerprint(public_b),'kind':'task','title':'Fictional workflow contract','text':'SYNTHETIC ONLY: Review a fictional community garden plan.','context':hashlib.sha256(b'workflow-ui-contract').hexdigest(),'task_id':'workflow-contract','expires':time.time()+900,'provider_disclosure':FIXTURE_GRANT},a)
            original=request(a_url,'GET','/api/items/'+task['id']+'/review',token=a)
            request(a_url,'POST','/api/items/'+task['id']+'/release',{'review_digest':original['review_digest']},a)
            request(a_url,'POST','/api/exchange',{},a);request(b_url,'POST','/api/exchange',{},b)
            incoming=request(b_url,'GET','/api/items/'+task['id']+'/review',token=b)
            request(b_url,'POST','/api/items/'+task['id']+'/decision',{'review_digest':incoming['review_digest'],'decision':'accept'},b)
            state=request(b_url,'GET','/api/state',token=b)
            item=next(item for item in state['items'] if item['id']==task['id'])
            accepted=request(b_url,'GET','/api/items/'+task['id']+'/review',token=b)
            records.append({'kind':'prepare','state':state,'item':item,'review':accepted})
            prepared=request(b_url,'POST','/api/items/'+task['id']+'/workflow',{},b)
            path='/api/workflows/'+prepared['run_id']
            review=request(b_url,'GET',path+'/review',token=b)
            records.append({'kind':'provider','state':request(b_url,'GET','/api/state',token=b),'item':item,'run':prepared,'review':review})
            approved=request(b_url,'POST',path+'/approve',{'review_digest':review['review_digest'],'expires':time.time()+300},b)
            records.append({'kind':'provider','state':request(b_url,'GET','/api/state',token=b),'item':item,'run':approved,'review':request(b_url,'GET',path+'/review',token=b)})
            completed=request(b_url,'POST',path+'/run',{'review_digest':review['review_digest']},b)
            result=request(b_url,'GET',path+'/result',token=b)
            records.append({'kind':'result','state':request(b_url,'GET','/api/state',token=b),'item':item,'run':completed,'review':result})
            staged=request(b_url,'POST',path+'/stage',{'review_digest':result['review_digest']},b)
            after=request(b_url,'GET','/api/state',token=b)
            assert next(i for i in after['items'] if i['id']==staged['artifact_id'])['state']=='draft'
            records.append({'kind':'status','state':after,'item':item,'run':staged})
    script="""
import fs from 'node:fs';
import {validateState,validateReview,canPrepareWorkflow,validateWorkflowStatus,validateWorkflowReview,validateWorkflowResult} from './pilot/web/model.mjs';
const records=JSON.parse(fs.readFileSync(0,'utf8'));
for(const record of records){
 validateState(record.state);
 if(record.kind==='prepare'){validateReview(record.review,record.item);if(!canPrepareWorkflow(record.state,record.item,record.review))throw new Error('Exact prepared task unavailable');}
 else{validateWorkflowStatus(record.run,record.item);if(record.kind==='provider')validateWorkflowReview(record.review,record.run,record.item,record.state.identity);if(record.kind==='result')validateWorkflowResult(record.review,record.run,record.item,record.state.peers.find(p=>p.peer_id===record.item.peer_id));}
}
console.log('PASS actual workflow HTTP-to-UI contract: accepted signed task, separate synthetic request approval and run, exact result review, draft-only artifact staging.');
"""
    checked=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(records),text=True,cwd=ROOT,capture_output=True,timeout=15)
    if checked.returncode:raise AssertionError('Workflow frontend contract mismatch: '+checked.stderr[-1600:])
    print(checked.stdout.strip())


if __name__=='__main__':run()
