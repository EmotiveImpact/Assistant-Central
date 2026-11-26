import copy
import unittest
from demo import fixture
from durable import LocalDelivery
from network import Denied
from bound_identity import BINDING_DOMAIN, IdentityRegistry, possession_digest, signed_bytes
from integrated_fixture import FixtureAuthorities
from sdk_transport_fixture import PinnedSdkFixture
from vendor.a4a_sdk.keys import Keys
from vendor.a4a_sdk import crypto


class BoundIdentityTests(unittest.TestCase):
    def setUp(self):
        self.meeting,_,_=fixture()
        self.a=FixtureAuthorities(self.meeting,1000)

    def resign(self, bindings, owner, private_key=None):
        key=private_key or self.a.transport_keys[owner]
        token=bindings[owner]
        token['transport_proof']=crypto.sign(possession_digest(token['binding']),key.privkey_hex)
        body={'binding':token['binding'],'transport_proof':token['transport_proof']}
        token['owner_signature']=self.a.owner_keys[owner].sign(signed_bytes(BINDING_DOMAIN,body)).hex()

    def test_valid_binding_proves_transport_possession_and_exact_owner_approval(self):
        registry=self.a.registry
        self.assertEqual(registry.public_keys['bob'],self.a.transport_keys['bob'].pubkey_hex)
        registry.permits('bob','alice',1000)
        registry.permits('alice','bob',1000)
        with self.assertRaises(Denied):registry.permits('charlie','bob',1000)

    def test_forged_owner_binding_signature_rejected(self):
        tokens=copy.deepcopy(self.a.bindings);tokens['bob']['owner_signature']='0'*128
        with self.assertRaises(Denied):IdentityRegistry(self.meeting,self.a.owner_roots,tokens)

    def test_owner_signature_does_not_replace_transport_key_possession(self):
        tokens=copy.deepcopy(self.a.bindings)
        tokens['bob']['transport_proof']='0'*128
        body={'binding':tokens['bob']['binding'],'transport_proof':tokens['bob']['transport_proof']}
        tokens['bob']['owner_signature']=self.a.owner_keys['bob'].sign(signed_bytes(BINDING_DOMAIN,body)).hex()
        with self.assertRaises(Denied):IdentityRegistry(self.meeting,self.a.owner_roots,tokens)

    def test_altered_owner_context_peers_and_lifetime_fail_closed(self):
        changes=({'owner':'dana'},{'context':'0'*64},{'receive_from':['unknown']},
                 {'receive_from':['alice','alice']},{'expires_at':1000000},{'version':True}, {'unexpected':'authority'})
        for change in changes:
            tokens=copy.deepcopy(self.a.bindings);tokens['bob']['binding'].update(change);self.resign(tokens,'bob')
            with self.subTest(change=change),self.assertRaises(Denied):IdentityRegistry(self.meeting,self.a.owner_roots,tokens)

    def test_binding_expiry_and_future_start_are_enforced(self):
        for when in (999,87400):
            with self.subTest(when=when),self.assertRaises(Denied):self.a.registry.permits('bob','alice',when)

    def test_registry_detaches_from_mutable_input(self):
        tokens=copy.deepcopy(self.a.bindings)
        registry=IdentityRegistry(self.meeting,self.a.owner_roots,tokens)
        tokens['bob']['binding']['transport_pubkey']='0'*64
        self.assertEqual(registry.public_keys['bob'],self.a.transport_keys['bob'].pubkey_hex)
        self.assertNotEqual(registry.bindings['bob'],tokens['bob'])

    def test_validly_signed_key_replacement_cannot_silently_change_pinned_registry(self):
        store=LocalDelivery(':memory:')
        try:
            self.a.registry.pin(store)
            tokens=copy.deepcopy(self.a.bindings);replacement=Keys()
            tokens['bob']['binding']['transport_pubkey']=replacement.pubkey_hex;self.resign(tokens,'bob',replacement)
            new=IdentityRegistry(self.meeting,self.a.owner_roots,tokens)
            with self.assertRaises(Denied):new.pin(store)
            self.a.registry.pin(store)
        finally:store.close()

    def test_shared_transport_key_cannot_impersonate_two_distinct_owners(self):
        tokens=copy.deepcopy(self.a.bindings)
        tokens['bob']['binding']['transport_pubkey']=self.a.transport_keys['alice'].pubkey_hex
        self.resign(tokens,'bob',self.a.transport_keys['alice'])
        with self.assertRaises(Denied):IdentityRegistry(self.meeting,self.a.owner_roots,tokens)

    def test_single_key_peer_cannot_sign_for_another_owner(self):
        _,agents,_=fixture()
        peer=PinnedSdkFixture.for_bound_peer(self.meeting,'alice',self.a.transport_keys['alice'],self.a.registry.public_keys)
        with self.assertRaises(Denied):peer.seal(agents[1].preview_availability(self.meeting),'delivery',1000)
        self.assertEqual(set(peer.keys),{'alice'})

    def test_wrong_private_key_cannot_open_bound_endpoint(self):
        with self.assertRaises(Denied):
            PinnedSdkFixture.for_bound_peer(self.meeting,'alice',self.a.transport_keys['bob'],self.a.registry.public_keys)

    def test_recipient_receive_permission_is_not_outbound_authority(self):
        _,agents,_=fixture();message=agents[1].preview_availability(self.meeting)
        signed=self.a.control('bob','send',{'recipient':'alice','envelope_digest':'0'*64,'pair_versions':[1,1]},1000)
        with self.assertRaises(Denied):self.a.registry.verify_delivery(signed,message)
