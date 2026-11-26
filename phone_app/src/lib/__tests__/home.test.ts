import { DemoBackend } from '../demo';
import { cardFor, cardStack, failedParts, paragraph, plainText, queueOf } from '../home';

async function signedIn() {
  const demo = new DemoBackend(Date.now() / 1000);
  await demo.signIn('demo');
  return { demo, state: await demo.state(), approvals: await demo.approvals() };
}

describe('Home', () => {
  it('puts the newest proposal first, then questions and messages, like the desktop', async () => {
    const { state, approvals } = await signedIn();
    const queue = queueOf(state, approvals);
    expect(queue.map(e => e.kind)).toEqual(['proposal', 'proposal', 'question', 'message']);
    expect(queue[0].title).toBe('Pay a £120 deposit to The Lido');
  });

  it('says who is asking, with the pair inline, and ends honestly', async () => {
    const { state, approvals } = await signedIn();
    const queue = queueOf(state, approvals);
    const segments = paragraph(state, queue, [], 15);
    expect(plainText(segments)).toBe('Afternoon Maya. Tom’s Tom and Otto Otto sent Pay a £120 deposit to The Lido and 3 more wait for you. Nothing else needs you.');
    expect(segments.some(s => 'pair' in s && s.pair.owner === 'Tom' && s.pair.agent === 'Otto')).toBe(true);
  });

  it('never claims nothing else needs you when part could not be checked', async () => {
    const { state, approvals } = await signedIn();
    const failed = failedParts(null, true);
    expect(plainText(paragraph(state, queueOf(state, approvals), failed, 9))).toMatch(/I couldn’t check your assistant’s questions just now\.$/);
  });

  it('is calm when nothing waits', async () => {
    const { state } = await signedIn();
    const quiet = { ...state, items: state.items.filter(i => i.state !== 'pending') };
    expect(plainText(paragraph(quiet, queueOf(quiet, null), [], 10))).toBe('Morning Maya. Nothing needs you right now.');
  });

  it('cycles cards with Not now and names each assistant beside its owner', async () => {
    const { state, approvals } = await signedIn();
    const queue = queueOf(state, approvals);
    expect(cardStack(state, queue, 1).map(c => c.entry.kind)).toEqual(['proposal', 'question', 'message']);
    expect(cardStack(state, queue, 4)[0].entry.key).toBe(queue[0].key);
    const result = cardFor(state, queue[1]);
    expect(result.who).toBe('Wren, Riya’s assistant');
    expect(result.team).toBe('Result for Calendar sync, part of Supper club app');
    expect(cardFor(state, queue[2]).who).toBe('Juniper, your assistant');
  });
});
