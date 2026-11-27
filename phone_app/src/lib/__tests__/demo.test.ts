import { DemoBackend } from '../demo';
import { attentionItems, columnOf, decisionRows, groupsOf, needsHold, roomLine, roomsOf, teamsOf } from '../../shared/web';

describe('The demo Parlu', () => {
  it('asks for a hold on money and refuses a changed review', async () => {
    const demo = new DemoBackend();
    await demo.signIn('demo');
    const state = await demo.state();
    const lido = state.items.find(i => i.title.startsWith('Pay a £120'))!;
    expect(needsHold(lido, 'accept')).toBe(true);
    expect(decisionRows(lido, { agent: 'Otto', owner: 'Tom', actions: ['accept'] })[0][1]).toBe("Up to £120.00 from this mission's limit. Simulated, no real payment.");
    const review = await demo.review(lido.id);
    await expect(demo.decide(lido.id, 'f'.repeat(64), 'accept')).rejects.toThrow();
    const result = await demo.decide(lido.id, review.review_digest, 'accept') as { decision_digest: string };
    expect(result.decision_digest).toMatch(/^[0-9a-f]{64}$/);
    await expect(demo.decide(lido.id, review.review_digest, 'accept')).rejects.toThrow();
  });

  it('moves a team mission part from Plan to Asked when it is sent, and a merged result to Done', async () => {
    const demo = new DemoBackend();
    await demo.signIn('demo');
    let team = teamsOf(await demo.state())[0];
    expect(team.parts.map((p: { step: string }) => p.step)).toEqual(['Building', 'Result', 'Plan']);
    const menu = team.parts[2].item, result = team.parts[1].result;
    await demo.release(menu.id, (await demo.review(menu.id)).review_digest);
    await demo.decide(result.id, (await demo.review(result.id)).review_digest, 'accept');
    team = teamsOf(await demo.state())[0];
    expect(team.parts.map((p: { step: string }) => p.step)).toEqual(['Building', 'Done', 'Asked']);
  });

  it('answers questions as information only, and only with a listed option', async () => {
    const demo = new DemoBackend();
    await demo.signIn('demo');
    await expect(demo.answer('q-quotes', 5)).rejects.toThrow();
    await expect(demo.answer('q-quotes', 0)).resolves.toMatchObject({ authority: 'information-only', answer: 'Wait for the quotes' });
    expect((await demo.approvals()).questions).toHaveLength(0);
  });

  it('makes an invite with a code and a link the desktop would accept', async () => {
    const demo = new DemoBackend();
    await demo.signIn('demo');
    const made = await demo.createInvite('Ada');
    if (!made.made) throw new Error('not made');
    expect(made.code).toMatch(/^\d{4}$/);
    const review = await demo.openInvite(made.link);
    expect(review.ok).toBe(true);
    if (review.ok) await expect(demo.acceptInvite(made.link, review.review_digest)).resolves.toMatchObject({ joined: true });
    expect((await demo.state()).relay?.invites).toHaveLength(1);
  });

  it('shows Sam’s 40th as a room with a change of mind, a passed vote and a vote for you', async () => {
    const demo = new DemoBackend();
    await demo.signIn('demo');
    const state = await demo.state();
    expect(teamsOf(state)).toHaveLength(1);
    const party = roomsOf(state).find(r => r.name === 'Sam’s 40th');
    expect(party.threads).toEqual(['Venue', 'Food', 'Asks']);
    const garden = party.entries.find((e: any) => e.type === 'note' && e.note.note === 'idea');
    expect(columnOf(garden)).toBeNull();
    expect(garden.replacedBy.note.why).toMatch(/Rain/);
    const lido = party.votes.find((v: any) => !v.incoming);
    expect(lido.result).toMatchObject({ yes: 3, total: 4, outcome: 'passed' });
    expect(roomLine(party)).toMatch(/^3 things need your yes\./);
    // Notes are read in the room, never queued on Home for a decision.
    expect(attentionItems(state).some(i => i.room?.record === 'note')).toBe(false);
    const cake = party.votes.find((v: any) => v.incoming);
    await demo.decide(cake.items[0].id, (await demo.review(cake.items[0].id)).review_digest, 'accept');
    const after = roomsOf(await demo.state()).find(r => r.name === 'Sam’s 40th');
    expect(columnOf(after.votes.find((v: any) => v.incoming))).toBe('done');
    expect(groupsOf(state)).toHaveLength(1);
  });
});
