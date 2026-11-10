"""Real HTTP owner controls, existing password accounts and no provider calls."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from pilot.auth import LocalOwnerAuth
from pilot.crypto import fingerprint, digest
from pilot.server import PilotHandler
from workspace_ui.conversation_service import ConversationConfig, VERSION, load_conversation_config
from workspace_ui.server import WorkspaceHTTPServer

PASSWORD='Fictional conversation password'


def fixture(root):
    keys={}
    for name in ('alice','bob','carol'):
        auth=LocalOwnerAuth(root/name)
        auth.bootstrap(name,name+'_assistant',PASSWORD)
        keys[name]=fingerprint(auth.public_identity())
        auth.close()
    (root/'ledger').mkdir(mode=0o700)
    config=ConversationConfig({'version':VERSION,'directory':str(root/'ledger'),
        'actors':[{'directory':str(root/n),'fingerprint':keys[n]} for n in ('bob','carol')]})
    return keys,config


class ConversationHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.keys,self.config=fixture(self.root)
        self.start()
        self.tokens={n:self.login(n) for n in self.keys}

    def start(self):
        self.server=WorkspaceHTTPServer(self.root/'alice',conversation_config=self.config)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown();self.thread.join();self.server.server_close()

    def tearDown(self):
        self.stop();self.tmp.cleanup()

    def request(self,method,path,value=None,token=None,headers=None,raw=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        h=dict(headers or {})
        if token:h['Authorization']='Bearer '+token
        if value is not None or raw is not None:h['Content-Type']='application/json'
        data=raw if raw is not None else json.dumps(value) if value is not None else None
        try:
            c.request(method,path,body=data,headers=h)
            r=c.getresponse();body=r.read()
            return r.status,json.loads(body)
        finally:c.close()

    def login(self,name):
        status,result=self.request('POST','/api/session',{'account':name,'password':PASSWORD})
        self.assertEqual(status,200,result);return result['token']

    def call(self,name,path,value=None,method=None,expect=200):
        status,result=self.request(method or ('GET' if value is None else 'POST'),path,value,self.tokens[name])
        self.assertEqual(status,expect,result);return result

    def bind(self,name):
        result=self.call(name,'/api/conversations/thread_1')['binding']
        return {k:result[k] for k in ('member_epoch','policy_generation')}

    def create(self):
        self.call('alice','/api/conversations',{'id':'thread_1'})

    def join(self,name):
        invite=self.call('alice','/api/conversations/thread_1/invite',{'binding':self.bind('alice'),'recipient':self.keys[name]})
        self.call(name,f"/api/conversations/invitations/{invite['id']}/accept",{})
        return invite

    def post(self,name,text,request_id='msg_1',binding=None):
        return self.call(name,'/api/conversations/thread_1/message',{'binding':binding or self.bind(name),'request_id':request_id,'text':text})

    def history(self,name,query=None):
        return self.call(name,'/api/conversations/thread_1/history',{'binding':self.bind(name),**({'query':query} if query else {})})['messages']

    def review(self,events,author='alice',recipient='carol',expires=None):
        return self.call(author,'/api/conversations/thread_1/grant-review',{'binding':self.bind(author),'recipient':self.keys[recipient],
            'event_ids':[e['id'] for e in events],'purpose':'Review exact local context','expires_at':expires or time.time()+600})

    def approve(self,review,name='alice',expect=200):
        return self.call(name,f"/api/conversations/grants/{review['statement']['id']}/approve",{'review_digest':review['review_digest']},expect=expect)

    def test_separate_actor_sessions_and_owner_runtime(self):
        for name in self.keys:
            state=self.call(name,'/api/state')
            self.assertEqual(state['identity']['owner_id'],name)
            self.assertTrue(state['conversations']['enabled'])
        self.assertEqual(self.request('POST','/api/session',{'account':'unknown','password':PASSWORD})[0],401)
        self.assertEqual(self.request('GET','/api/conversations',token='x'*43)[0],401)
        self.create()
        self.assertEqual(self.call('bob','/api/conversations')['rooms'],[])
        self.call('bob','/api/conversations/thread_1',expect=400)

    def test_future_only_join_read_search_context_and_repeat_post(self):
        self.create();self.join('bob')
        old=self.post('alice','hidden archaeology title')
        invite=self.call('alice','/api/conversations/thread_1/invite',{'binding':self.bind('alice'),'recipient':self.keys['carol']})
        self.assertEqual(self.call('carol','/api/conversations')['rooms'],[])
        self.call('bob',f"/api/conversations/invitations/{invite['id']}/accept",{},expect=400)
        self.call('carol',f"/api/conversations/invitations/{invite['id']}/accept",{})
        self.assertEqual(self.history('carol'),[]);self.assertEqual(self.history('carol','archaeology'),[])
        self.call('carol','/api/conversations/thread_1/read',{'binding':self.bind('carol'),'event_id':old['id']},expect=400)
        self.call('carol','/api/conversations/thread_1/context',{'binding':self.bind('carol'),'event_ids':[old['id']]},expect=400)
        future=self.post('bob','future visible',request_id='future')
        self.assertEqual(self.post('bob','future visible',request_id='future')['id'],future['id'])
        self.assertEqual([x['id'] for x in self.history('carol')],[future['id']])
        self.assertNotIn('archaeology',json.dumps(self.call('carol','/api/conversations')))
        self.assertNotIn('count',json.dumps(self.call('carol','/api/conversations')))

    def test_exact_source_author_grant_and_revoke(self):
        self.create();self.join('bob');old=self.post('alice','exact old words');other=self.post('bob','Bobs earlier words')
        self.join('carol')
        self.review([old])
        self.call('alice','/api/conversations/thread_1/grant-review',{'binding':self.bind('alice'),'recipient':self.keys['carol'],'event_ids':[other['id']],
            'purpose':'Not mine','expires_at':time.time()+600},expect=400)
        review=self.review([old]);self.assertEqual(review['messages'][0]['text'],'exact old words')
        self.approve(review,'bob',expect=400)
        altered={'statement':review['statement'],'review_digest':review['review_digest']}
        self.call('alice',f"/api/conversations/grants/{review['statement']['id']}/approve",altered,expect=400)
        self.approve(review);self.approve(review)
        self.assertEqual(self.history('carol')[0]['id'],old['id'])
        self.assertEqual(self.call('bob','/api/conversations/thread_1/grants')['grants'],[])
        self.call('bob',f"/api/conversations/grants/{review['statement']['id']}/revoke",{},expect=400)
        self.call('alice',f"/api/conversations/grants/{review['statement']['id']}/revoke",{})
        self.assertEqual(self.history('carol'),[])
        self.approve(review,expect=400)

    def test_stale_composer_and_review_membership_change(self):
        self.create();self.join('bob');old=self.post('alice','before group')
        stale=self.bind('alice');self.join('carol')
        self.call('alice','/api/conversations/thread_1/message',{'binding':stale,'request_id':'old_draft','text':'private DM draft'},expect=400)
        r=self.review([old]);self.call('alice','/api/conversations/thread_1/remove',{'binding':self.bind('alice'),'recipient':self.keys['carol']})
        self.approve(r,expect=400);self.join('carol');self.approve(r,expect=400)
        self.assertEqual(self.history('carol'),[])

    def test_review_bound_to_exact_session_and_lost_on_restart(self):
        self.create();old=self.post('alice','message');self.join('carol');review=self.review([old])
        another=self.login('alice')
        self.assertEqual(self.request('POST',f"/api/conversations/grants/{review['statement']['id']}/approve",{'review_digest':review['review_digest']},another)[0],400)
        self.stop();self.start();self.tokens={n:self.login(n) for n in self.keys}
        self.approve(review,expect=400)
        self.assertEqual(self.history('alice')[0]['text'],'message')

    def test_coordinator_logout_and_expiry_deny_even_empty_search(self):
        self.create();self.join('bob')
        self.call('alice','/api/session',{},method='DELETE')
        self.call('bob','/api/conversations',expect=400)
        self.assertEqual(self.call('bob','/api/state')['identity']['owner_id'],'bob')
        self.tokens['alice']=self.login('alice');self.assertTrue(self.call('bob','/api/conversations')['rooms'])
        def expire():
            auth=self.server.owner.primary.auth
            auth._db.execute('UPDATE sessions SET expires=0');auth._db.commit()
        self.server.owner_worker.submit(expire).result()
        self.call('bob','/api/conversations/thread_1/history',{'binding':{'member_epoch':'unknown','policy_generation':1}},expect=400)
        self.call('bob','/api/conversations',expect=400)

    def test_actor_expiry_and_forged_actor_or_origin_denied(self):
        self.create();self.join('bob')
        self.call('bob','/api/conversations',{'id':'new','principal':self.keys['alice']},expect=400)
        self.assertEqual(self.request('POST','/api/conversations',{'id':'x'},self.tokens['alice'],{'Origin':'https://evil.invalid'})[0],400)
        self.assertEqual(self.request('GET','/api/conversations',token=self.tokens['alice'],headers={'Host':'evil.invalid'})[0],400)
        self.assertEqual(self.request('POST','/api/conversations',token=self.tokens['alice'],raw='{"id":"x","id":"y"}')[0],400)
        self.call('bob','/api/session',{},method='DELETE');self.call('bob','/api/conversations',expect=401)

    def test_pagination_and_bounds(self):
        self.create()
        for i in range(26):self.post('alice',f'word {i}',request_id=f'r{i}')
        first=self.history('alice');self.assertEqual(len(first),25)
        result=self.call('alice','/api/conversations/thread_1/history',{'binding':self.bind('alice'),'after':first[-1]['id']})
        self.assertEqual(len(result['messages']),1)
        self.call('alice','/api/conversations/thread_1/history',{'binding':self.bind('alice'),'after':'unknown'},expect=400)
        self.call('alice','/api/conversations/thread_1/history',{'binding':self.bind('alice'),'query':'x'*257},expect=400)
        self.call('alice','/api/conversations/thread_1/message',{'binding':self.bind('alice'),'request_id':'big','text':'a'*16385},expect=400)

    def test_expired_grant_hidden_and_status(self):
        self.create();old=self.post('alice','expiry message');self.join('carol')
        r=self.review([old],expires=time.time()+30);self.approve(r)
        def advance():
            ledger=self.server.owner.ledger
            ledger.clock=lambda:time.time()+31
        self.server.owner_worker.submit(advance).result()
        self.assertEqual(self.history('carol'),[])
        self.assertEqual(self.call('alice','/api/conversations/thread_1/grants')['grants'][0]['status'],'expired')

    def test_account_config_pins_and_private_file(self):
        value={'version':VERSION,'directory':str(self.root/'ledger'),'actors':[{'directory':str(self.root/'bob'),'fingerprint':self.keys['bob']}]}
        path=self.root/'config.json';path.write_text(json.dumps(value));path.chmod(0o600)
        self.assertEqual(load_conversation_config(path).actors[0]['fingerprint'],self.keys['bob'])
        path.chmod(0o644)
        with self.assertRaises(Exception):load_conversation_config(path)
        value['actors'][0]['directory']='relative'
        with self.assertRaises(Exception):ConversationConfig(value)

    def outcome(self,name,request_id,text,binding=None,expect=200,room='thread_1'):
        return self.call(name,f'/api/conversations/{room}/message-outcome',{
            'binding':binding or self.bind(name),'request_id':request_id,
            'expected_request_digest':digest({'kind':'message','text':text,'source_ids':[]})},expect=expect)

    def test_exact_message_outcome_after_real_committed_http_response_loss(self):
        self.create();self.join('bob');binding=self.bind('alice')
        text='One fictional café ☕\n"message" / \\ with a lost response.'
        original=PilotHandler._reply
        def drop_committed_reply(handler,status,value,content_type='application/json'):
            if handler.path=='/api/conversations/thread_1/message' and status==200:
                handler.close_connection=True
                return
            return original(handler,status,value,content_type)
        ledger=self.server.owner.ledger
        with patch.object(ledger,'append',wraps=ledger.append) as append:
            with patch.object(PilotHandler,'_reply',drop_committed_reply):
                with self.assertRaises(http.client.RemoteDisconnected):
                    self.post('alice',text,request_id='lost_reply',binding=binding)
            self.assertEqual(append.call_count,1)
            before=self.server.owner_worker.submit(lambda:[tuple(row) for row in ledger.db.execute(
                'SELECT id,conversation_id,author,request_id,request_digest,body FROM conversation_events')]).result()
            first=self.outcome('alice','lost_reply',text,binding=binding)
            self.assertEqual(first['status'],'committed');self.assertEqual(first['event']['text'],text)
            self.assertEqual(first['event']['author'],self.keys['alice'])
            self.assertEqual(first['event']['conversation_id'],'thread_1')
            self.assertEqual(self.outcome('alice','lost_reply',text,binding=binding),first)
            self.assertEqual(append.call_count,1,'read-only inspection must never replay append')
            after=self.server.owner_worker.submit(lambda:[tuple(row) for row in ledger.db.execute(
                'SELECT id,conversation_id,author,request_id,request_digest,body FROM conversation_events')]).result()
            self.assertEqual(before,after);self.assertEqual(len(after),1)
            self.assertEqual([m['id'] for m in self.history('bob')],[first['event']['id']])
            self.assertEqual(set(first['event']),{'id','conversation_id','author','kind','text','sources','provenance_digest','trust','execution_authority'})

    def test_exact_message_outcome_absence_and_foreign_owner_never_disclose(self):
        self.create();self.join('bob');binding=self.bind('alice')
        self.assertEqual(self.outcome('alice','absent','No proof of rollback',binding),{'status':'inconclusive'})
        original=self.post('alice','Alice private words',request_id='same_request')
        self.assertEqual(self.outcome('bob','same_request','Alice private words'),{'status':'inconclusive'})
        own=self.post('bob','Bob different words',request_id='same_request')
        self.outcome('bob','same_request','Alice private words',expect=400)
        self.assertEqual(self.outcome('bob','same_request','Bob different words')['event']['id'],own['id'])
        self.assertEqual(self.outcome('alice','same_request','Alice private words',binding)['event']['id'],original['id'])
        self.call('alice','/api/conversations',{'id':'other_room'})
        other=self.call('alice','/api/conversations/other_room')['binding']
        self.assertEqual(self.outcome('alice','same_request','Alice private words',
            {k:other[k] for k in ('member_epoch','policy_generation')},room='other_room'),{'status':'inconclusive'})

    def test_exact_message_outcome_rejects_wrong_digest_binding_owner_and_shape(self):
        self.create();self.join('bob');binding=self.bind('alice');self.post('alice','Exact text',request_id='request')
        body={'binding':binding,'request_id':'request','expected_request_digest':digest({'kind':'message','text':'Exact text','source_ids':[]})}
        self.assertEqual(self.call('alice','/api/conversations/thread_1/message-outcome',body)['status'],'committed')
        changes=[{'expected_request_digest':'a'*64},{'expected_request_digest':'A'*64},{'expected_request_digest':'a'*63},
                 {'expected_request_digest':None},{'request_id':'invalid/request'},
                 {'binding':{**binding,'member_epoch':'not_original'}},{'binding':{**binding,'policy_generation':True}},
                 {'binding':{**binding,'policy_generation':binding['policy_generation']+1}},
                 {'principal':self.keys['bob']},{'text':'Exact text'}]
        for changed in changes:
            with self.subTest(changed=changed):self.call('alice','/api/conversations/thread_1/message-outcome',{**body,**changed},expect=400)
        self.call('alice','/api/conversations/thread_1/message-outcome',method='GET',expect=400)
        self.assertEqual(self.request('POST','/api/conversations/thread_1/message-outcome',body)[0],401)
        self.assertEqual(self.request('POST','/api/conversations/thread_1/message-outcome',body,self.tokens['alice'],{'Origin':'https://evil.invalid'})[0],400)

    def test_exact_message_outcome_stale_membership_and_rejoin_are_denied(self):
        self.create();self.join('bob');alice=self.bind('alice');bob=self.bind('bob')
        self.post('alice','Before group',request_id='alice_request',binding=alice)
        self.post('bob','Before leaving',request_id='bob_request',binding=bob)
        self.join('carol');self.outcome('alice','alice_request','Before group',alice,expect=400)
        self.call('bob','/api/conversations/thread_1/remove',{'binding':self.bind('bob'),'recipient':self.keys['bob']})
        self.outcome('bob','bob_request','Before leaving',bob,expect=400)
        self.join('bob');self.outcome('bob','bob_request','Before leaving',bob,expect=400)
        self.outcome('bob','bob_request','Before leaving',self.bind('bob'),expect=400)

    def test_exact_message_outcome_logout_relogin_and_coordinator_expiry(self):
        self.create();self.join('bob');binding=self.bind('bob');self.post('bob','Bob committed',request_id='request',binding=binding)
        old_token=self.tokens['bob'];self.call('bob','/api/session',{},method='DELETE')
        self.outcome('bob','request','Bob committed',binding,expect=401)
        self.tokens['bob']=self.login('bob');self.assertNotEqual(self.tokens['bob'],old_token)
        # A fresh explicit server read is authorised by this new session; the UI
        # separately discards old-session recovery tickets and never carries them.
        self.assertEqual(self.outcome('bob','request','Bob committed',binding)['status'],'committed')
        self.call('alice','/api/session',{},method='DELETE')
        self.outcome('bob','request','Bob committed',binding,expect=400)
        self.tokens['alice']=self.login('alice')
        self.assertEqual(self.outcome('bob','request','Bob committed',binding)['status'],'committed')
        def expire():
            auth=self.server.owner.primary.auth
            auth._db.execute('UPDATE sessions SET expires=0');auth._db.commit()
        self.server.owner_worker.submit(expire).result()
        self.outcome('bob','request','Bob committed',binding,expect=400)
        self.assertEqual(self.call('bob','/api/state')['identity']['owner_id'],'bob')
        def expire_actor():
            auth=self.server.owner.services[self.keys['bob']].auth
            auth._db.execute('UPDATE sessions SET expires=0');auth._db.commit()
        self.server.owner_worker.submit(expire_actor).result()
        self.outcome('bob','request','Bob committed',binding,expect=401)

    def test_exact_message_outcome_unavailable_read_can_be_repeated_without_a_send(self):
        self.create();binding=self.bind('alice');self.post('alice','Saved once',request_id='request',binding=binding)
        ledger=self.server.owner.ledger
        with patch.object(ledger,'append',wraps=ledger.append) as append:
            with patch.object(ledger,'inspect_message_outcome',side_effect=RuntimeError('Fictional read unavailable')):
                self.outcome('alice','request','Saved once',binding,expect=503)
            self.assertEqual(self.outcome('alice','request','Saved once',binding)['status'],'committed')
            self.assertEqual(append.call_count,0)
        self.assertEqual(len(self.history('alice')),1)
