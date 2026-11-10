"""Check frontend schema against two actual local HTTP services, not a browser.

All accounts and text are disposable fiction. No tokens/passwords are exported
to the JavaScript validation process, filesystem evidence or stdout.
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


def run():
    records = []
    with tempfile.TemporaryDirectory(prefix='pilot-ui-contract-') as directory:
        a_dir, b_dir = Path(directory)/'first', Path(directory)/'second'
        password_a, public_a = provision(a_dir, 'fictional-a', 'atlas')
        password_b, public_b = provision(b_dir, 'fictional-b', 'beacon')
        with running_process(a_dir) as (a_url,_), running_process(b_dir) as (b_url,_):
            a = request(a_url,'POST','/api/session',{'password':password_a})['token']
            b = request(b_url,'POST','/api/session',{'password':password_b})['token']
            for url, token, peer_url, public in ((a_url,a,b_url,public_b),(b_url,b,a_url,public_a)):
                request(url,'POST','/api/peers',{'public_identity':public,'expected_fingerprint':fingerprint(public),'endpoint':peer_url},token)
            item = request(a_url,'POST','/api/proposals',{
                'peer_id':fingerprint(public_b),'kind':'task','title':'Fictional contract check',
                'text':'SYNTHETIC ONLY: A fictional garden task.',
                'context':hashlib.sha256(b'fictional-contract').hexdigest(),
                'task_id':'contract-task','expires':time.time()+900},a)
            def capture(url,token):
                state=request(url,'GET','/api/state',token=token)
                review=request(url,'GET','/api/items/'+item['id']+'/review',token=token)
                records.append({'state':state,'review':review,'item':next(i for i in state['items'] if i['id']==item['id'])})
                return review
            def sync(url,token):request(url,'POST','/api/exchange',{},token)
            draft=capture(a_url,a)
            request(a_url,'POST','/api/items/'+item['id']+'/release',{'review_digest':draft['review_digest']},a)
            sync(a_url,a);sync(b_url,b)
            pending=capture(b_url,b)
            request(b_url,'POST','/api/items/'+item['id']+'/decision',{'review_digest':pending['review_digest'],'decision':'accept'},b)
            accepted=capture(b_url,b)
            request(b_url,'POST','/api/items/'+item['id']+'/cancel',{'review_digest':accepted['review_digest']},b)
            capture(b_url,b)
            for url,token in ((a_url,a),(b_url,b)):
                request(url,'DELETE','/api/session',{},token)
    script = """
import fs from 'node:fs';
import {validateState,validateReview} from './pilot/web/model.mjs';
const records=JSON.parse(fs.readFileSync(0,'utf8'));
for(const record of records){validateState(record.state);validateReview(record.review,record.item);}
console.log('PASS actual HTTP-to-UI contract: draft, pending, accepted, cancelled, withheld content and logout across two separate processes.');
"""
    result=subprocess.run(['node','--input-type=module','-e',script],input=json.dumps(records),text=True,cwd=ROOT,capture_output=True,timeout=15)
    if result.returncode:
        raise AssertionError('Frontend contract did not match actual HTTP state: '+result.stderr[-1000:])
    print(result.stdout.strip())


if __name__ == '__main__':run()
