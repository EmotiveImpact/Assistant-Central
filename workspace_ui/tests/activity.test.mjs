import test from 'node:test';
import assert from 'node:assert/strict';
import {activityLine, activityIsYours} from '../activity.mjs';

const peers = [{peer_id: 'p1', owner_id: 'casey', agent_id: 'Mira'}];
const items = [
  {id: 'a', peer_id: 'p1', kind: 'task', title: 'Print the launch posters'},
  {id: 'b', peer_id: 'p1', kind: 'artifact', title: 'Poster proofs'},
];
const line = (event, data) => activityLine({event, item_id: 'a', data}, {items, peers});

test('each saved event reads as one plain sentence with real names', () => {
  assert.equal(line('proposal_received', {}), 'Mira asked you: “Print the launch posters”');
  assert.equal(line('proposal_created', {}), 'You drafted “Print the launch posters” for Casey');
  assert.equal(line('proposal_released', {}), 'You sent “Print the launch posters” to Mira');
  assert.equal(line('recipient_decided', {decision: 'accept'}), 'You agreed to “Print the launch posters”');
  assert.equal(line('recipient_decided', {decision: 'reject'}), 'You turned down “Print the launch posters”');
  assert.equal(line('peer_decision_observed', {decision: 'accepted'}), 'Casey agreed to “Print the launch posters”');
  assert.equal(line('cancellation_requested', {}), 'You withdrew “Print the launch posters”');
  assert.equal(line('peer_cancellation_observed', {}), 'Mira withdrew “Print the launch posters”');
  assert.equal(line('proposal_received', {cancelled: true}), 'Mira sent “Print the launch posters” and then withdrew it');
});

test('results and connections have their own words', () => {
  assert.equal(activityLine({event: 'proposal_received', item_id: 'b'}, {items, peers}), 'Mira returned “Poster proofs”');
  assert.equal(activityLine({event: 'peer_enrolled', data: {peer: 'p1'}}, {items, peers}), 'You connected with Casey and Mira');
});

test('unknown events and missing records still read sensibly', () => {
  assert.equal(activityLine({event: 'workflow_result_staged'}, {}), 'Workflow result staged');
  assert.equal(activityLine({event: 'proposal_received', item_id: 'gone'}, {items, peers}), 'Their assistant asked you: “Untitled”');
  assert.equal(activityLine(null), 'Saved event');
});

test('your own actions are marked as yours', () => {
  assert.equal(activityIsYours({event: 'recipient_decided'}), true);
  assert.equal(activityIsYours({event: 'proposal_received'}), false);
});
