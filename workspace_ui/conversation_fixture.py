"""Fresh fictional owner accounts for HTTP/browser acceptance, never real owners."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile

from conversation import ConversationLedger
from pilot.auth import LocalOwnerAuth
from pilot.crypto import fingerprint
from .conversation_service import ConversationConfig, VERSION
from .server import WorkspaceHTTPServer

PASSWORD = 'Fictional conversation password'


def seed_conversations(root):
    root=Path(root)
    with ExitStack() as cleanup:
        auths={};tokens={};keys={}
        for name in ('alice','bob','carol'):
            auth=LocalOwnerAuth(root/name);cleanup.callback(auth.close)
            auth.bootstrap(name,name+'_assistant',PASSWORD)
            auths[name]=auth;tokens[name]=auth.login(PASSWORD);keys[name]=fingerprint(auth.public_identity())
        ledger=ConversationLedger(root/'ledger',auths['alice'],{keys[n]:a for n,a in auths.items()})
        cleanup.callback(ledger.close)
        ledger.create(keys['alice'],tokens['alice'],'thread_1')
        invitation=ledger.invite(keys['alice'],tokens['alice'],'thread_1',keys['bob'])
        ledger.accept_invitation(keys['bob'],tokens['bob'],invitation['id'])
        for author,text,request_id in [('alice','Only Alice and Bob saw this earlier plan.','old_alice'),
            ('alice','<img src=x onerror="window.conversationXss=true"> Exact inert words.','hostile'),
            ('bob','Bobs earlier words need Bobs own permission.','old_bob')]:
            ledger.append(keys[author],tokens[author],ledger.bind_context(keys[author],tokens[author],'thread_1'),request_id=request_id,text=text)
        ledger.invite(keys['alice'],tokens['alice'],'thread_1',keys['carol'])
    return ConversationConfig({'version':VERSION,'directory':str(root/'ledger'),'actors':[
        {'directory':str(root/name),'fingerprint':keys[name]} for name in ('bob','carol')]})


def main():
    parser=argparse.ArgumentParser(description='Disposable fictional conversation UI acceptance')
    parser.add_argument('--port',type=int,default=8778)
    args=parser.parse_args()
    if args.port!=0 and not 1024<=args.port<=65535:parser.error('Loopback port required')
    with tempfile.TemporaryDirectory(prefix='central-conversation-ui-') as temporary:
        root=Path(temporary);config=seed_conversations(root)
        server=WorkspaceHTTPServer(root/'alice',args.port,conversation_config=config)
        print(json.dumps({'url':server.origin,'synthetic_only':True,'provider_calls':False}),flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
        finally:server.server_close()


if __name__=='__main__':main()
