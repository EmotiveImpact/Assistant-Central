import test from 'node:test';
import assert from 'node:assert/strict';
import {validateListing, validateDraftReview, describeEntry, MODES} from '../approvals.mjs';

const digest = 'a'.repeat(64);
const listing = () => ({
  note: 'Nothing here is sent, shared or agreed until you choose.',
  messages: [{draft_id: 'd1', assistant_id: 'bob-assistant', conversation_id: 'room1', text: 'Hello', digest, trust: 'assistant-written'}],
  questions: [{question_id: 'q1', question: 'Thursday or Friday?', options: ['Thursday', 'Friday'], state: 'waiting', expires_at: 1, authority: 'information-only'}],
  drafts: [{draft_id: 'p1', conversation_id: 'room1', text: 'Plan', revision: 1, execution_authority: false}],
  drafts_available: true, count: 3,
});

test('a well-formed listing is accepted', () => {
  assert.equal(validateListing(listing()).count, 3);
});

test('a listing that miscounts, or a draft claiming authority, is refused', () => {
  assert.throws(() => validateListing({...listing(), count: 2}));
  const bad = listing(); bad.drafts[0].execution_authority = true;
  assert.throws(() => validateListing(bad));
  const shortDigest = listing(); shortDigest.messages[0].digest = 'abc';
  assert.throws(() => validateListing(shortDigest));
  const oneOption = listing(); oneOption.questions[0].options = ['Only'];
  assert.throws(() => validateListing(oneOption));
});

test('a draft review must match the draft asked for', () => {
  const review = {draft_id: 'p1', text: 'Plan', revision: 1, people: ['Bob'], review_digest: digest, scope: 'Agreeing to this exact text only.'};
  assert.equal(validateDraftReview(review, 'p1').draft_id, 'p1');
  assert.throws(() => validateDraftReview(review, 'p2'));
});

test('timeline entries read as plain sentences', () => {
  assert.equal(describeEntry({seq: 1, role: 'your_assistant', kind: 'message_proposed'}), 'Your assistant proposed a message for you to check');
  assert.equal(describeEntry({seq: 2, role: 'you', kind: 'question_answered'}), 'You answered a question');
  assert.equal(describeEntry({seq: 3, role: 'system', kind: 'something_new'}), 'Central something new');
  assert.equal(Object.keys(MODES).length, 3);
});
