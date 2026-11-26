"""Team mission records over a real local relay: rules, results, merge approval and access."""
import hashlib
import json
import time
import unittest

from pilot import team
from pilot.tests.test_relay_link import RelayLinkTests

BRIEF = 'SYNTHETIC ONLY: build the fictional card deposits screen.'


def result_text(part, kept=True, compute=12_000, summary='SYNTHETIC ONLY: card deposits are ready.'):
    checks = [{'rule': rule, 'side': side, 'kept': kept} for side in ('must', 'must_not') for rule in part['rules'][side]]
    value = {'summary': summary, 'checks': checks,
             'compute_used': None if compute is None else {'micro': compute, 'currency': 'GBP'}}
    return team.RESULT + json.dumps(value)


class TeamRecordTests(RelayLinkTests):
    def setUp(self):
        super().setUp()
        self.connect(self.edem, self.maya)
        self.context = hashlib.sha256(b'Fictional supper club app').hexdigest()

    def send(self, sender, recipient, kind, title, text, task_id, parent_id=None):
        item = sender.runtime.propose(sender.session, recipient.fingerprint, kind, title, text, self.context,
                                      task_id, time.time() + (2000 if parent_id else 3000), parent_id=parent_id)
        review = sender.runtime.review(sender.session, item['id'])
        sender.runtime.release(sender.session, item['id'], review['review_digest'])
        self.assertEqual(sender.sync(send=True)['sent'], 1)
        self.assertEqual(recipient.sync(send=False)['received'], 1)
        return item['id']

    def decide(self, owner, item_id, decision='accept'):
        review = owner.runtime.review(owner.session, item_id)
        return owner.runtime.decide(owner.session, item_id, review['review_digest'], decision)

    def agreed_part(self, compute={'cap_micro': 500_000, 'currency': 'GBP'}):
        text = team.part_text(BRIEF, ['Tests pass'], ['Store card numbers'], compute)
        item = self.send(self.edem, self.maya, 'task', 'Supper club app: Card deposits', text, 'team-cards')
        self.assertEqual(self.maya.runtime.review(self.maya.session, item)['content'], text)
        self.decide(self.maya, item)
        self.maya.sync(send=True)
        self.edem.sync(send=False)
        return item, team.read_part(text)

    def test_a_part_with_rules_is_agreed_and_its_result_merged(self):
        item, part = self.agreed_part()
        result = self.send(self.maya, self.edem, 'artifact', 'Result: Card deposits', result_text(part),
                           'team-cards', parent_id=item)
        status = self.edem.runtime.status(self.edem.session, item)
        self.assertEqual(status['team'], {'record': 'part', 'rules': part['rules'], 'compute': part['compute']})
        returned = self.edem.runtime.status(self.edem.session, result)['team']
        self.assertEqual((returned['record'], returned['compute_used']), ('result', {'micro': 12_000, 'currency': 'GBP'}))
        self.assertTrue(all(check['kept'] for check in returned['checks']))
        merged = self.decide(self.edem, result)
        self.assertEqual(merged['state'], 'accepted')
        self.assertTrue(merged['decision_digest'])  # The lead's signed merge approval is the receipt.

    def test_a_result_must_report_on_every_rule_of_its_part(self):
        item, part = self.agreed_part()
        short = json.loads(result_text(part)[len(team.RESULT):])
        short['checks'] = short['checks'][:1]
        with self.assertRaises(ValueError):
            self.maya.runtime.propose(self.maya.session, self.edem.fingerprint, 'artifact', 'Result',
                                      team.RESULT + json.dumps(short), self.context, 'team-cards',
                                      time.time() + 2000, parent_id=item)
        with self.assertRaises(ValueError):  # A plain reply cannot skip the checks either.
            self.maya.runtime.propose(self.maya.session, self.edem.fingerprint, 'artifact', 'Result',
                                      'SYNTHETIC ONLY: done.', self.context, 'team-cards', time.time() + 2000,
                                      parent_id=item)

    def test_compute_is_reported_only_in_the_parts_currency(self):
        item, part = self.agreed_part(compute=None)
        with self.assertRaises(ValueError):
            self.maya.runtime.propose(self.maya.session, self.edem.fingerprint, 'artifact', 'Result',
                                      result_text(part), self.context, 'team-cards', time.time() + 2000,
                                      parent_id=item)
        self.send(self.maya, self.edem, 'artifact', 'Result', result_text(part, compute=None), 'team-cards',
                  parent_id=item)

    def test_access_is_asked_for_one_agreed_part_and_granted_by_the_lead(self):
        item, _ = self.agreed_part()
        ask = {'part_task_id': 'team-cards', 'what': 'Read the fictional supper club calendar',
               'why': 'SYNTHETIC ONLY: deposits follow the booking dates.', 'hours': 24}
        request = self.send(self.maya, self.edem, 'task', 'Access: supper club calendar',
                            team.ACCESS + json.dumps(ask), 'team-access-1')
        granted = self.decide(self.edem, request)
        self.assertEqual(granted['state'], 'accepted')
        for unknown in ({**ask, 'part_task_id': 'team-unknown'}, {**ask, 'hours': 999}):
            with self.assertRaises(ValueError):
                self.maya.runtime.propose(self.maya.session, self.edem.fingerprint, 'task', 'Access',
                                          team.ACCESS + json.dumps(unknown), self.context, 'team-access-2',
                                          time.time() + 3000)

    def test_malformed_parts_and_stray_results_are_refused(self):
        bad = [team.PART + json.dumps({'brief': BRIEF, 'rules': {'must': ['A', 'A'], 'must_not': []}, 'compute': None}),
               team.PART + json.dumps({'brief': BRIEF, 'rules': {'must': [], 'must_not': []}, 'compute': {'cap_micro': 0, 'currency': 'GBP'}}),
               team.PART + '{not json', team.RESULT + '{}']
        for index, text in enumerate(bad):
            with self.assertRaises(ValueError):
                self.edem.runtime.propose(self.edem.session, self.maya.fingerprint, 'task', 'Bad part', text,
                                          self.context, f'team-bad-{index}', time.time() + 3000)


def load_tests(loader, tests, pattern):
    # Only this file's tests: the relay link tests already run on their own.
    return loader.loadTestsFromNames([f'{__name__}.TeamRecordTests.{name}' for name in
                                      loader.getTestCaseNames(TeamRecordTests) if name.startswith('test_') and
                                      name in TeamRecordTests.__dict__])
