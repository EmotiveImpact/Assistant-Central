"""Trusted-local organization and lifetime fences, never identity or authority.

The containing OwnerWorkspace holds its RLock for every call. No I/O or service
calls occur here. The integrity seal detects accidental in-memory corruption; it
is not authentication against code with access to this Python process.
"""
import copy
import re
from network import Denied, digest

MAX_GROUPS = 8
MAX_MEMBERS = 10
AFTER_STOP_ACTIONS = frozenset({'check', 'recover', 'decline', 'defer', 'withdraw_unused'})
AFTER_STOP_AGENT_METHODS = frozenset({'proposal_status', 'inbox'})


class RelationshipWorkspace:
    def __init__(self, resolve):
        self._resolve = resolve
        self._groups = {}
        self._revision = 0
        self._stopped = frozenset()
        self._seal = self._fingerprint()

    def _fingerprint(self):
        return digest({'groups': self._groups, 'revision': self._revision,
                       'stopped': sorted(self._stopped)})

    def validate(self):
        try:
            if self._seal != self._fingerprint():
                raise Denied('Relationship workspace integrity mismatch')
            for group in self._groups.values():
                for member in group['members']:
                    self._member(member)
        except (KeyError, TypeError, ValueError, RecursionError) as exc:
            raise Denied('Relationship workspace integrity mismatch') from exc

    @staticmethod
    def _id(value):
        if type(value) is not str or not re.fullmatch(r'group-[a-z0-9][a-z0-9-]{0,47}', value):
            raise Denied('Expected bounded immutable group ID')
        return value

    def _member(self, value):
        if type(value) is not dict or set(value) != {'selector', 'context'}:
            raise Denied('Expected exact selector and context membership')
        if any(type(v) is not str for v in value.values()):
            raise Denied('Expected exact string selector and context')
        self._resolve(value['selector'], value['context'])
        return dict(value)

    def _members(self, values):
        if type(values) is not list or not 1 <= len(values) <= MAX_MEMBERS:
            raise Denied('Expected bounded nonempty exact membership')
        members = [self._member(v) for v in values]
        if len({v['context'] for v in members}) != len(members):
            raise Denied('Duplicate task membership')
        return sorted(members, key=lambda v: (v['selector'], v['context']))

    def _group(self, group_id):
        self._id(group_id)
        if group_id not in self._groups:
            raise Denied('Unknown exact group ID')
        return self._groups[group_id]

    def stopped(self, selector, context):
        self.validate()
        return (selector, context) in self._stopped

    def require_work(self, selector, context):
        if self.stopped(selector, context):
            raise Denied('Local relationship fence prevents further task work')

    def groups(self):
        self.validate()
        return copy.deepcopy(list(self._groups.values()))

    @staticmethod
    def _review(value):
        value = copy.deepcopy(value)
        value['review_digest'] = digest({'domain': 'relationship-owner-review/v1', **value})
        return value

    def preview(self, request):
        self.validate()
        if type(request) is not dict or type(request.get('operation')) is not str:
            raise Denied('Expected closed relationship preview')
        op = request['operation']
        if op == 'create' and set(request) == {'operation', 'spec'}:
            spec = request['spec']
            if type(spec) is not dict or set(spec) != {'group_id', 'label', 'members'}:
                raise Denied('Expected exact group specification')
            gid = self._id(spec['group_id'])
            label = spec['label']
            if type(label) is not str or not 1 <= len(label) <= 80 or label != label.strip() or any(ord(c)<32 or 0xD800<=ord(c)<=0xDFFF for c in label):
                raise Denied('Expected bounded inert group label')
            members = self._members(spec['members'])
            if gid in self._groups or len(self._groups) >= MAX_GROUPS:
                raise Denied('Group ID occupied or lifetime capacity reached')
            for m in members:
                self.require_work(**m)
            return self._review({'operation':op, 'registry_revision':self._revision,
                                 'group_id':gid, 'label':label, 'revision':1, 'members':members})
        if op == 'attach' and set(request) == {'operation', 'group_id', 'member'}:
            group = self._group(request['group_id'])
            member = self._member(request['member'])
            if group['stopped'] or len(group['members']) >= MAX_MEMBERS or member in group['members']:
                raise Denied('Group stopped, membership occupied, or capacity reached')
            for existing in group['members']:
                self.require_work(**existing)
            self.require_work(**member)
            return self._review({'operation':op, 'group_id':group['group_id'],
                                 'revision':group['revision'], 'members':group['members'], 'member':member})
        if op == 'stop' and set(request) == {'operation', 'group_id'}:
            group = self._group(request['group_id'])
            if group['stopped']:
                return copy.deepcopy(group['stop_review'])
            return self._review({'operation':op, 'group_id':group['group_id'],
                                 'revision':group['revision'], 'members':group['members']})
        raise Denied('Unknown relationship operation or unexpected fields')

    def commit(self, operation, review, confirmation):
        self.validate()
        phrases = {'create':'CREATE GROUP', 'attach':'ATTACH TASK', 'stop':'STOP GROUP'}
        if type(operation) is not str or operation not in phrases or type(confirmation) is not str or confirmation != phrases[operation]:
            raise Denied('Type the exact relationship confirmation')
        if type(review) is not dict or review.get('operation') != operation:
            raise Denied('Expected the exact relationship review')
        try:
            if operation == 'create':
                request = {'operation':operation, 'spec':{k:review[k] for k in ('group_id','label','members')}}
            else:
                request = {'operation':operation, 'group_id':review['group_id']}
                if operation == 'attach':request['member'] = review['member']
            checked = self.preview(request)
            # Canonical JSON digest comparison also distinguishes True from 1.
            if set(review) != set(checked) or digest(review) != digest(checked):
                raise Denied('Relationship review changed; review exact membership again')
        except (KeyError, TypeError, ValueError, RecursionError) as exc:
            raise Denied('Expected exact closed relationship review') from exc
        gid = checked['group_id']
        if operation == 'create':
            self._groups[gid] = {k:copy.deepcopy(checked[k]) for k in ('group_id','label','revision','members')}
            self._groups[gid].update(stopped=False, stop_review=None)
        elif operation == 'attach':
            group = self._groups[gid]
            group['members'] = self._members(group['members'] + [checked['member']])
            group['revision'] += 1
        else:
            group = self._groups[gid]
            if group['stopped']:return copy.deepcopy(group)
            # Commit the local fence before any subsequent linked-service route.
            self._stopped |= frozenset((m['selector'], m['context']) for m in group['members'])
            group['stopped'] = True
            group['stop_review'] = copy.deepcopy(checked)
            group['revision'] += 1
        self._revision += 1
        self._seal = self._fingerprint()
        return copy.deepcopy(self._groups[gid])
