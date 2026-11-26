"""Loopback-only owner browser fixture. No remote services or real identities.

Start with: python local_owner_app.py
Keep this launcher running. Closing a browser tab does not destroy state, but
stopping the launcher or choosing Discard fixture destroys temporary keys/records.
Local host processes are trusted. Host/Origin checks are not human authentication.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import threading
from urllib.parse import parse_qs, urlsplit
from network import Denied
from owner_ui_service import OwnerUIService

STATIC=Path(__file__).resolve().parent/'owner_ui'
MAX_BODY=8192
CSP="default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'; object-src 'none'"


class LoopbackServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=False
    def __init__(self,service,port=0,workspace=False):
        if type(port) is not int or not 0<=port<=65535:raise ValueError('Invalid local port')
        self.service=service
        self.handler_slots=threading.BoundedSemaphore(8)
        super().__init__(('127.0.0.1',port),WorkspaceHandler if workspace else Handler)
        self.expected_host=f'127.0.0.1:{self.server_address[1]}'
        self.origin='http://'+self.expected_host

    def process_request(self, request, client_address):
        if not self.handler_slots.acquire(blocking=False):
            request.close()  # No handler or application action ran.
            return
        try:super().process_request(request,client_address)
        except BaseException:
            self.handler_slots.release();raise

    def process_request_thread(self, request, client_address):
        try:super().process_request_thread(request,client_address)
        finally:self.handler_slots.release()


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.0'
    static_root=STATIC
    post_routes=('/api/action',)
    def setup(self):
        super().setup();self.connection.settimeout(5)
    def log_message(self,*args):pass  # Never log request bodies or approval data.
    def reply(self,status,value,mime='application/json; charset=utf-8'):
        data=json.dumps(value,ensure_ascii=True,allow_nan=False).encode() if mime.startswith('application/json') else value
        self.send_response(status)
        self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('Content-Security-Policy',CSP)
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','DENY');self.send_header('Cross-Origin-Resource-Policy','same-origin')
        self.send_header('Permissions-Policy','camera=(), microphone=(), geolocation=()')
        self.end_headers();self.wfile.write(data)
    def host_ok(self):
        return self.headers.get_all('Host')==[self.server.expected_host]
    def guard(self,write=False):
        if not self.host_ok():raise Denied('Only the exact loopback host is accepted')
        origins=self.headers.get_all('Origin')
        if (write and origins!=[self.server.origin]) or (origins and origins!=[self.server.origin]):
            raise Denied('Cross-origin requests are forbidden')
        if self.headers.get('Sec-Fetch-Site') not in (None,'same-origin','none'):
            raise Denied('Cross-site requests are forbidden')
        if write:
            if self.headers.get_all('Content-Type')!=['application/json'] or self.headers.get_all('X-Owner-Fixture')!=['v7']:
                raise Denied('Only the local JSON interface may submit actions')
            if self.headers.get('Transfer-Encoding') is not None:raise Denied('Chunked request bodies are not supported')
    def do_GET(self):
        try:
            self.guard();target=urlsplit(self.path)
            if target.scheme or target.netloc:raise Denied('Absolute request URLs are forbidden')
            static={'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
            if target.path in static and not target.query:
                file,mime=static[target.path];return self.reply(200,(self.static_root/file).read_bytes(),mime)
            params=parse_qs(target.query,strict_parsing=True,keep_blank_values=True)
            if any(len(v)!=1 for v in params.values()):raise Denied('Duplicate query fields are forbidden')
            if any(not v[0] for v in params.values()):raise Denied('Empty query fields are forbidden')
            result=self.read_api(target.path,params)
            if result is not None:return self.reply(200,result)
            self.reply(404,{'error':'No such local fixture resource'})
        except (Denied,ValueError,TypeError,KeyError) as exc:self.reply(400,{'error':str(exc)})
        except (RuntimeError,BrokenPipeError,OSError):self.reply(503,{'error':'Fixture unavailable. No automatic action was retried.'})
    def read_api(self,path,params):
        if path=='/api/state' and set(params)=={'owner'}:
            return self.server.service.state(params['owner'][0])
        if path in ('/api/review','/api/delivery') and set(params)=={'owner','id'}:
            method=self.server.service.review if path=='/api/review' else self.server.service.delivery
            return method(params['owner'][0],params['id'][0])
        return None

    def do_POST(self):
        try:
            self.guard(write=True)
            if self.path not in self.post_routes:return self.reply(404,{'error':'No such action route'})
            lengths=self.headers.get_all('Content-Length')
            if not lengths or len(lengths)!=1 or not lengths[0].isdigit():raise Denied('One bounded Content-Length is required')
            size=int(lengths[0])
            if not 1<=size<=MAX_BODY:raise Denied('Action body exceeds the local fixture limit')
            data=self.rfile.read(size)
            if len(data)!=size:raise Denied('Incomplete action body')
            def unique(pairs):
                out={}
                for key,value in pairs:
                    if key in out:raise Denied('Duplicate JSON fields are forbidden')
                    out[key]=value
                return out
            def finite_float(value):
                parsed=float(value)
                if not math.isfinite(parsed):raise Denied('Nonfinite JSON is forbidden')
                return parsed
            body=json.loads(data,object_pairs_hook=unique,parse_float=finite_float,
                            parse_constant=lambda _: (_ for _ in ()).throw(Denied('Nonfinite JSON is forbidden')))
            result=self.post_api(self.path,body)
            self.reply(200,result)
            if result.get('closed'):threading.Thread(target=self.server.shutdown,daemon=True).start()
        except (Denied,ValueError,TypeError,KeyError,RecursionError,UnicodeDecodeError) as exc:self.reply(400,{'error':str(exc)})
        except (RuntimeError,BrokenPipeError,OSError):self.reply(503,{'error':'Fixture unavailable. Outcome may be uncertain; inspect state, do not blindly repeat the action.'})
    def post_api(self,path,body):
        return self.server.service.action(body)
    def do_OPTIONS(self):self.reply(405,{'error':'Cross-origin/preflight access is not supported'})
    def do_PUT(self):self.reply(405,{'error':'Unsupported method'})
    do_DELETE=do_PUT


class WorkspaceHandler(Handler):
    """Same bounded HTTP/security envelope, separate closed routing and assets."""
    static_root=Path(__file__).resolve().parent/'workspace_ui'
    post_routes=('/api/action','/api/task-preview','/api/relationship-preview','/api/continuity-preview')

    def post_api(self,path,body):
        if path=='/api/continuity-preview':
            return self.server.service.continuity_preview(body)
        if path=='/api/relationship-preview':
            return self.server.service.relationship_preview(body)
        if path=='/api/task-preview':
            if type(body) is not dict or set(body)!={'spec'}:
                raise Denied('Task preview requires only an exact composition spec')
            return self.server.service.task_preview(body['spec'])
        return self.server.service.action(body)

    def read_api(self,path,params):
        if path=='/api/continuity' and not params:
            return self.server.service.continuity_state()
        if path=='/api/relationships' and not params:
            return self.server.service.relationships()
        if path=='/api/tasks' and not params:
            return self.server.service.tasks()
        fields={'selector','context','owner'}
        if path=='/api/messages' and set(params)==fields:
            return self.server.service.received_messages(params['selector'][0],params['context'][0],params['owner'][0])
        if path=='/api/response-context' and set(params)==fields:
            return self.server.service.response_context(params['selector'][0],params['context'][0],params['owner'][0])
        if path in ('/api/state','/api/proposals') and set(params)==fields:
            method=self.server.service.state if path=='/api/state' else self.server.service.proposals
            return method(params['selector'][0],params['context'][0],params['owner'][0])
        if path in ('/api/review','/api/delivery') and set(params)==fields|{'id'}:
            method=self.server.service.review if path=='/api/review' else self.server.service.delivery
            return method(params['selector'][0],params['context'][0],params['owner'][0],params['id'][0])
        return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=0,help='Loopback port; default chooses a free ephemeral port')
    parser.add_argument('--workspace',action='store_true',help='Use the separate disposable two-task workspace; no services start until Create')
    parser.add_argument('--continuity',action='store_true',help='Opt in to fictional informational continuity; requires --workspace')
    args=parser.parse_args()
    if args.continuity and not args.workspace:
        parser.error('--continuity requires --workspace')
    if args.workspace:
        from workspace_ui_service import WorkspaceUIService
        service=WorkspaceUIService(continuity=args.continuity)
    else:service=OwnerUIService()
    server=None
    try:
        server=LoopbackServer(service,args.port,workspace=args.workspace)
        print('LOCAL_OWNER_URL='+server.origin,flush=True)
        print('Fictional fixture only. No real authentication. Keep this launcher running; stopping it discards temporary keys and records.',flush=True)
        server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:pass
    finally:
        if server:server.server_close()
        service.close()
        print('Local fixture stopped. Temporary records and generated fixture keys discarded.',flush=True)


if __name__=='__main__':main()
