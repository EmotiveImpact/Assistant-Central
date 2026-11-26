import copy
import unittest
from unittest.mock import patch
from owner_workspace import OwnerWorkspace
from network import Denied, digest
from continuity_proofs import verify_certificate, review, OWNER_DOMAIN, CONTINUITY_DOMAIN
from bound_identity import verify_owner


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.w=OwnerWorkspace(continuity=True)
        self.addCleanup(self.w.close)

    def commit(self,op,r):
        return self.w.continuity_commit(op,r,{'enroll':'ENROLL','associate':'ASSOCIATE','retire':'RETIRE'}[op]+' CONTINUITY '+r['review_digest'])

    def enroll(self,iid='fictional-one'):
        r=self.w.continuity_preview({'operation':'enroll','identity_id':iid})
        self.commit('enroll',r); return r

    def task(self,n=0):
        r=self.w.list_tasks()[n];self.w.create(r['selector'],r['context']);return r

    def preview(self,t,aid='proof-one'):
        return self.w.continuity_preview({'operation':'associate','identity_id':'fictional-one','association_id':aid,
            'selector':t['selector'],'context':t['context'],'actor':t['requester']})

    def test_pure_preview_explicit_enrollment_and_distinct_roots(self):
        before=self.w.list_tasks()
        p=self.w.continuity_preview({'operation':'enroll','identity_id':'fictional-one'})
        self.assertEqual(self.w.continuity_state()['identities'],[])
        self.commit('enroll',p);self.assertEqual(before,self.w.list_tasks());self.assertEqual(self.w._slots,{})
        a=self.task();b=self.task(1)
        pa=self.preview(a);state=self.w.continuity_state();self.preview(a)
        self.assertEqual(state,self.w.continuity_state())
        ca=self.commit('associate',pa)['certificate']
        cb=self.commit('associate',self.preview(b,'proof-two'))['certificate']
        self.assertNotEqual(ca['body']['owner_root'],cb['body']['owner_root'])
        sa=self.w._slots[a['selector']]['service']; sb=self.w._slots[b['selector']]['service']
        self.assertNotEqual(sa.requests[a['requester']]['binding']['transport_pubkey'],
                            sb.requests[b['requester']]['binding']['transport_pubkey'])
        self.assertEqual(ca['body']['continuity_root'],cb['body']['continuity_root'])
        for c in (ca,cb):
            self.assertEqual(c,verify_certificate(c,self.w.continuity_state()['incarnation']))
        wrong=copy.deepcopy(cb);wrong['owner_signature']=ca['owner_signature']
        with self.assertRaises(Denied):verify_certificate(wrong,self.w.continuity_state()['incarnation'])
        with self.assertRaises(Denied):verify_owner(ca['body']['owner_root'],CONTINUITY_DOMAIN,ca['body'],ca['owner_signature'])
        # No bindings, pairing, proposals or transport signing occurred.
        for slot in self.w._slots.values():self.assertEqual(slot['service'].bindings,{})

    def test_review_alteration_staleness_and_restart(self):
        self.enroll();t=self.task();p=self.preview(t)
        altered=copy.deepcopy(p);altered['body']['association_id']='changed';altered=review(altered['body'])
        with self.assertRaises(Denied):self.commit('associate',altered)
        self.enroll('fictional-two')
        with self.assertRaises(Denied):self.commit('associate',p)
        p=self.preview(t)
        with patch('continuity_workspace.time.time',return_value=p['body']['review_expires_at']):
            with self.assertRaises(Denied):self.commit('associate',p)
        c=self.commit('associate',p)['certificate']
        other=OwnerWorkspace(continuity=True);self.addCleanup(other.close)
        with self.assertRaises(Denied):verify_certificate(c,other.continuity_state()['incarnation'])

    def test_retire_keeps_history_not_task_cancellation(self):
        self.enroll();t=self.task();p=self.preview(t);self.commit('associate',p)
        r=self.w.continuity_preview({'operation':'retire','identity_id':'fictional-one'})
        self.commit('retire',r)
        row=self.commit('associate',p);self.assertEqual(row['status'],'retired');self.assertFalse(row['active'])
        self.assertIsNotNone(row['certificate']);self.assertEqual(self.w.list_tasks()[0]['phase'],'open')
        self.assertFalse(self.w.list_tasks()[0]['local_work_stopped'])
        with self.assertRaises(Denied):self.preview(t,'proof-two')
        self.assertEqual(self.commit('retire',r),self.w.continuity_state())
        changed=copy.deepcopy(p);changed['body']['nonce']='a'*64;changed=review(changed['body'])
        with self.assertRaises(Denied):self.commit('associate',changed)

    def test_expired_closed_and_stopped_are_historical(self):
        self.enroll();t=self.task();p=self.preview(t);self.commit('associate',p)
        with patch('continuity_workspace.time.time',return_value=p['body']['certificate_expires_at']):
            self.assertEqual(self.commit('associate',p)['status'],'expired')
        g=self.w.relationship_preview({'operation':'create','spec':{'group_id':'group-stop','label':'Same name is not identity','members':[{k:t[k] for k in ('selector','context')}]}})
        self.w.relationship_commit('create',g,'CREATE GROUP')
        pending=self.preview(t,'proof-pending')
        g=self.w.relationship_preview({'operation':'stop','group_id':'group-stop'});self.w.relationship_commit('stop',g,'STOP GROUP')
        with self.assertRaises(Denied):self.commit('associate',pending)
        self.assertEqual(self.commit('associate',p)['status'],'stopped')
        self.w.close_task(t['selector'],t['context'])
        self.assertEqual(self.commit('associate',p)['status'],'closed')

    def test_uncertain_no_resign_and_cleanup_independence(self):
        self.enroll();t=self.task();p=self.preview(t)
        signer=self.w._continuity.identities['fictional-one']['signer']
        with patch.object(signer,'request',side_effect=RuntimeError('lost response')) as fail:
            with self.assertRaises(RuntimeError):self.commit('associate',p)
            self.assertEqual(self.commit('associate',p)['status'],'uncertain')
            self.assertEqual(fail.call_count,1)
        self.assertIsNone(self.w.continuity_state()['associations'][0]['certificate'])
        with patch.object(signer,'close',side_effect=RuntimeError('cleanup')):
            r=self.w.continuity_preview({'operation':'retire','identity_id':'fictional-one'})
            with self.assertRaises(RuntimeError):self.commit('retire',r)
            with self.assertRaises(Denied):self.preview(t,'proof-two')
            self.w.close_task(t['selector'],t['context'])
            self.assertEqual(self.w.list_tasks()[0]['phase'],'closed')
        self.commit('retire',r)

    def test_maximum_custom_selectors_both_capabilities(self):
        from generic_capabilities import BOUNDED_TEXT
        self.enroll()
        for n,text in enumerate((False,True)):
            spec={'selector':'custom-'+chr(97+n)*48,'task_id':'task-'+str(n),
                  'conversation_id':'conversation-'+str(n),'requester':'alice',
                  'query':'Fictional bounded test'}
            if text:spec.update(capability=BOUNDED_TEXT,max_reply_chars=100)
            else:spec.update(max_items=2)
            reviewed=self.w.task_preview(spec)
            task=self.w.compose(spec,reviewed['review_digest'],'CREATE TASK')
            row=self.commit('associate',self.preview(task,'proof-custom-'+str(n)))
            self.assertEqual(row['status'],'active')
            self.assertEqual(row['certificate']['body']['selector'],spec['selector'])

    def test_opt_in_closed_schema_and_detachment(self):
        off=OwnerWorkspace();self.addCleanup(off.close)
        with self.assertRaises(Denied):off.continuity_state()
        for bad in ({'operation':'enroll','identity_id':'one','extra':1},[],{'operation':'associate'}):
            with self.assertRaises(Denied):self.w.continuity_preview(bad)
        self.enroll();s=self.w.continuity_state();s['identities'].clear()
        self.assertEqual(len(self.w.continuity_state()['identities']),1)
        for n in range(3):self.enroll('fictional-'+str(n))
        with self.assertRaises(Denied):self.enroll('fictional-full')

if __name__=='__main__':unittest.main()
