"""Optional trusted-local continuity registry. Caller holds workspace RLock.

This stores public evidence and subprocess handles, never task-owner or continuity private signing keys. The
registry is disposable, bounded and does not participate in task authorization.
"""
import copy
import secrets
import hmac
import hashlib
import time
from network import Denied, digest
from fixture_ipc import JsonProcess
from continuity_proofs import (MAX_IDENTITIES, MAX_ASSOCIATIONS, PURPOSE, detached,
    identifier, hex64, selector, review, validate_body, verify_certificate)


class ContinuityWorkspace:
    def __init__(self, workspace):
        self.w = workspace
        self.incarnation = secrets.token_hex(32)
        self.identities = {}
        self.history = {}
        self.generation = 0
        self._preview_secret = secrets.token_bytes(32)

    def _open(self):
        if self.w.closed: raise Denied('Workspace closed')

    def _identity(self, identity_id):
        identifier(identity_id)
        if identity_id not in self.identities: raise Denied('Unknown enrolled continuity identity')
        return self.identities[identity_id]

    def _active(self, identity_id):
        self._open()
        i = self._identity(identity_id)
        if i['phase'] != 'active': raise Denied('Continuity identity unavailable or retired')
        return i

    def _review(self, body):
        return {**body,'review_digest':digest({'domain':'fictional-continuity-management-review/v1',**body})}

    def preview(self, request):
        self._open(); r=detached(request)
        if type(r) is not dict: raise Denied('Expected closed continuity request')
        op=r.get('operation')
        if op=='enroll' and set(r)=={'operation','identity_id'}:
            iid=identifier(r['identity_id'])
            if iid in self.identities or len(self.identities)>=MAX_IDENTITIES: raise Denied('Identity occupied or lifetime capacity reached')
            return self._review({'operation':op,'incarnation':self.incarnation,'identity_id':iid,'generation':self.generation})
        if op=='retire' and set(r)=={'operation','identity_id'}:
            i=self._identity(r['identity_id'])
            if i.get('retire_review'): return detached(i['retire_review'])
            return self._review({'operation':op,**i['anchor']})
        if op=='associate' and set(r)=={'operation','identity_id','association_id','selector','context','actor'}:
            i=self._active(r['identity_id']); aid=identifier(r['association_id'])
            if aid in self.history or len(self.history)>=MAX_ASSOCIATIONS: raise Denied('Association occupied or lifetime capacity reached')
            selector(r['selector']); identifier(r['actor']); hex64(r['context'])
            service=self._service(r['selector'],r['context'],r['actor'])
            now=int(time.time())
            b={'purpose':PURPOSE,**i['anchor'],'association_id':aid,'selector':r['selector'],
               'context':r['context'],'actor':r['actor'],'owner_root':service.roots[r['actor']],
               'nonce':secrets.token_hex(32),'generation':self.generation,'issued_at':now,
               'review_expires_at':now+120,'certificate_expires_at':now+86400}
            salt=secrets.token_hex(16)
            b['nonce']=salt+self._nonce_mac(b,salt)
            return review(b)
        raise Denied('Unknown continuity operation or extra fields')

    def _nonce_mac(self,b,salt):
        return hmac.new(self._preview_secret, (salt+digest({k:v for k,v in b.items() if k!='nonce'})).encode('ascii'), hashlib.sha256).hexdigest()[:32]

    def _service(self, selector, context, actor):
        self.w._require_work(selector,context)
        service=self.w._service(selector,context)
        if type(actor) is not str or service.closed or actor not in service.roots: raise Denied('Existing fictional task owner required')
        return service

    def _row(self, aid):
        h=self.history[aid]; b=h['review']['body']; status=h['phase']
        if status=='proven':
            if self.identities[b['identity_id']]['phase']!='active': status='retired'
            elif self.w.closed: status='closed'
            elif self.w._slots[b['selector']]['phase']!='open': status='closed'
            elif self.w._relationships.stopped(b['selector'],b['context']): status='stopped'
            elif int(time.time())>=b['certificate_expires_at']: status='expired'
            else: status='active'
        return detached({'association_id':aid,'status':status,'active':status=='active',
                         'historical':True,'review':h['review'],'certificate':h['certificate']})

    def state(self):
        return copy.deepcopy({'incarnation':self.incarnation,'identities':[
            {'anchor':i['anchor'],'phase':i['phase'],'cleanup':i['cleanup']} for i in self.identities.values()],
            'associations':[self._row(aid) for aid in self.history]})

    def commit(self, operation, supplied, confirmation):
        r=detached(supplied)
        if type(operation) is not str or operation not in ('enroll','associate','retire') or type(r) is not dict:
            raise Denied('Expected closed continuity commit')
        phrase={'enroll':'ENROLL CONTINUITY','associate':'ASSOCIATE CONTINUITY','retire':'RETIRE CONTINUITY'}[operation]
        if type(confirmation) is not str or confirmation!=phrase+' '+str(r.get('review_digest','')):
            raise Denied('Confirm exact continuity review digest')
        if operation=='associate': return self._associate(r)
        iid=identifier(r.get('identity_id'))
        if operation=='enroll' and iid in self.identities:
            i=self.identities[iid]
            if digest(r)!=digest(i['enroll_review']): raise Denied('Changed enrollment ID reuse')
            return self.state()
        expected=self.preview({'operation':operation,'identity_id':iid})
        if digest(expected)!=digest(r): raise Denied('Stale or changed continuity review')
        if operation=='retire':
            i=self._identity(iid)
            if i.get('retire_review') is not None and i['cleanup']=='disposed': return self.state()
            i['retire_review']=r; i['phase']='retired'; self.generation+=1
            self._dispose(i)
            return self.state()
        self._open()
        i={'anchor':{'incarnation':self.incarnation,'identity_id':iid,'identity_version':1},
           'phase':'uncertain','cleanup':'uncertain','signer':None,'enroll_review':r}
        self.identities[iid]=i; self.generation+=1
        try:
            child=JsonProcess('continuity_fixture_process.py','--incarnation',self.incarnation,'--identity-id',iid)
            i['signer']=child
            startup=child.read()
            if type(startup) is not dict or set(startup)!={'public_key','fixture_only'} or startup['fixture_only'] is not True:
                raise Denied('Unexpected continuity startup')
            from continuity_proofs import hex64
            root=hex64(startup['public_key'])
            i['anchor'].update(continuity_root=root,fingerprint=digest({'continuity_root':root}))
            i['phase']='active'; i['cleanup']='live'
        except BaseException:
            try:self._dispose(i)
            except Exception:pass
            raise
        return self.state()

    def _associate(self,r):
        if set(r)!={'body','review_digest'}: raise Denied('Expected exact association review')
        b=validate_body(r['body']); aid=b['association_id']
        if digest(r)!=digest(review(b)): raise Denied('Changed association review')
        if aid in self.history:
            if digest(r)!=digest(self.history[aid]['review']): raise Denied('Changed association ID reuse')
            return self._row(aid)
        if not hmac.compare_digest(b['nonce'][32:],self._nonce_mac(b,b['nonce'][:32])): raise Denied('Association preview was altered')
        i=self._active(b['identity_id'])
        if len(self.history)>=MAX_ASSOCIATIONS: raise Denied('Association lifetime capacity reached')
        if any(b[k]!=v for k,v in i['anchor'].items()) or b['generation']!=self.generation:
            raise Denied('Stale association anchor or generation')
        if not b['issued_at']<=int(time.time())<b['review_expires_at']: raise Denied('Review acceptance window expired')
        service=self._service(b['selector'],b['context'],b['actor'])
        if b['owner_root']!=service.roots[b['actor']]: raise Denied('Wrong existing task-owner root')
        # Pin BEFORE either IPC write. Any uncertain outcome consumes this slot.
        self.history[aid]={'phase':'uncertain','review':r,'certificate':None}
        self.generation+=1
        with service.lock:
            one=service.signers[b['actor']].request({'continuity_proof':b,'anchor':i['anchor'],'confirmation':'ASSOCIATE '+digest(b)})
            if type(one) is not dict or set(one)!={'ok','signature'} or one['ok'] is not True: raise Denied('Owner proof failed; association uncertain')
            from bound_identity import verify_owner
            from continuity_proofs import OWNER_DOMAIN
            verify_owner(b['owner_root'],OWNER_DOMAIN,b,one['signature'])
            two=i['signer'].request({'continuity_proof':b,'confirmation':'ASSOCIATE '+digest(b)})
            if type(two) is not dict or set(two)!={'ok','signature'} or two['ok'] is not True: raise Denied('Continuity proof failed; association uncertain')
            cert=verify_certificate({'body':b,'owner_signature':one['signature'],'continuity_signature':two['signature']},self.incarnation)
            # A response arriving after the reviewed window never activates evidence.
            # Recheck all local fences even though ordinary routes share this lock.
            if not b['issued_at']<=int(time.time())<b['review_expires_at']:
                raise Denied('Review expired during proof collection; association uncertain')
            if self._active(b['identity_id']) is not i or self._service(b['selector'],b['context'],b['actor']) is not service:
                raise Denied('Association target changed during proof collection')
            if service.roots[b['actor']]!=b['owner_root']:
                raise Denied('Task-owner root changed during proof collection')
            self.history[aid].update(phase='proven',certificate=cert)
        return self._row(aid)

    def _dispose(self,i):
        i['cleanup']='uncertain'
        if i['signer'] is not None: i['signer'].close()
        i['cleanup']='disposed'

    def close(self):
        failures=[]
        for i in self.identities.values():
            i['phase']='retired'
            try:self._dispose(i)
            except Exception: failures.append(i['anchor']['identity_id'])
        if failures: raise RuntimeError('Continuity cleanup uncertain: '+', '.join(failures))
