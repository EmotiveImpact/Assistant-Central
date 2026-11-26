"""Disposable offline fictional continuity signer. No task authority commands."""
from offline_guard import install
install()
import argparse
import json
import sys
import time
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from network import Denied, digest
from bound_identity import signed_bytes
from continuity_proofs import CONTINUITY_DOMAIN, validate_body, hex64, identifier
from fixture_ipc import _unique_object, _reject_constant


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--fixture',required=True,action='store_true')
    p.add_argument('--incarnation',required=True)
    p.add_argument('--identity-id',required=True)
    a=p.parse_args(); hex64(a.incarnation); identifier(a.identity_id)
    key=Ed25519PrivateKey.generate(); root=key.public_key().public_bytes_raw().hex()
    print(json.dumps({'public_key':root,'fixture_only':True}),flush=True)
    used=set()
    for line in iter(lambda:sys.stdin.buffer.readline(16385),b''):
        if len(line)>16384 or not line.endswith(b'\n'): return
        try:
            r=json.loads(line,object_pairs_hook=_unique_object,parse_constant=_reject_constant)
            if type(r) is not dict or set(r)!={'continuity_proof','confirmation'}: raise Denied('Closed proof command required')
            b=validate_body(r['continuity_proof'])
            if (b['incarnation']!=a.incarnation or b['identity_id']!=a.identity_id or b['continuity_root']!=root
                or not b['issued_at']<=int(time.time())<b['review_expires_at']): raise Denied('Wrong anchor or stale proof')
            if r['confirmation']!='ASSOCIATE '+digest(b): raise Denied('Exact proof confirmation required')
            if b['association_id'] in used or len(used)>=20: raise Denied('No proof signing retries')
            used.add(b['association_id'])
            print(json.dumps({'ok':True,'signature':key.sign(signed_bytes(CONTINUITY_DOMAIN,b)).hex()}),flush=True)
        except (Denied,ValueError,TypeError,KeyError,RecursionError):
            print(json.dumps({'ok':False,'error':'Continuity proof rejected'}),flush=True)

if __name__=='__main__': main()
