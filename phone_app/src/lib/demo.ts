// A built-in Parlu with fictional people, so the app can be tried without a computer running
// Parlu. It answers in exactly the shapes the real owner API uses, so every screen runs the
// same code either way. Nothing here leaves the phone. Every name and amount is made up.
import type {
  Approvals, Backend, DraftReview, Identity, InviteMade, InviteReview, Item, Peer, Review, State, TimelineEntry,
} from './types';
import { inviteFromText } from '../shared/web';

const hex = (seed: string) => {
  // A stable, fake 64-character id from a short seed. Not a real digest.
  let h1 = 0x811c9dc5, out = '';
  for (let round = 0; out.length < 64; round++) {
    for (const ch of seed + round) { h1 ^= ch.charCodeAt(0); h1 = Math.imul(h1, 0x01000193) >>> 0; }
    out += h1.toString(16).padStart(8, '0');
  }
  return out.slice(0, 64);
};

const PASSWORD_HINT = 'demo';
const wait = (ms = 220) => new Promise(resolve => setTimeout(resolve, ms));

type Story = {
  identity: Identity;
  peers: Peer[];
  items: Item[];
  content: Record<string, string>;
  approvals: Approvals;
  timeline: TimelineEntry[];
  invites: NonNullable<State['relay']>['invites'];
};

function peer(owner: string, agent: string): Peer {
  const id = hex('peer:' + owner);
  return { peer_id: id, fingerprint: id, owner_id: owner, agent_id: agent, state: 'active' };
}

export function demoStory(now = Date.now() / 1000): Story {
  const tom = peer('Tom', 'Otto'), riya = peer('Riya', 'Wren'), kofi = peer('Kofi', 'Pip'), sam = peer('Sam', 'Bramble');
  const hour = 3600;
  const supper = hex('context:supper-club');
  const base = { parent_id: null, expires: now + 3 * 86400 };
  const items: Item[] = [
    { ...base, id: hex('lido'), kind: 'task', direction: 'incoming', state: 'pending', historical_state: 'pending',
      title: 'Pay a £120 deposit to The Lido', context: hex('context:sams-40th'), peer_id: tom.peer_id, created_at: now - 0.4 * hour,
      task_id: 'SAM-40', mission_cap: { cap_micro: 120_000_000, currency: 'GBP' } },
    { ...base, id: hex('part:deposits'), kind: 'task', direction: 'outgoing', state: 'accepted', historical_state: 'accepted',
      title: 'Supper club app: Card deposits', context: supper, peer_id: tom.peer_id, created_at: now - 26 * hour,
      team: { record: 'part', rules: { must: ['Use the test card keys only'], must_not: ['Store card numbers'] }, compute: { cap_micro: 8_000_000, currency: 'GBP' } } },
    { ...base, id: hex('part:calendar'), kind: 'task', direction: 'outgoing', state: 'accepted', historical_state: 'accepted',
      title: 'Supper club app: Calendar sync', context: supper, peer_id: riya.peer_id, created_at: now - 25 * hour,
      team: { record: 'part', rules: { must: ['Read only access to the shared calendar'], must_not: ['Email guests'] }, compute: null } },
    { ...base, id: hex('part:menu'), kind: 'task', direction: 'outgoing', state: 'draft', historical_state: 'draft',
      title: 'Supper club app: Menu page', context: supper, peer_id: kofi.peer_id, created_at: now - 24 * hour,
      team: { record: 'part', rules: { must: ['Match the Parlu look'], must_not: ['Add tracking'] }, compute: { cap_micro: 5_000_000, currency: 'GBP' } } },
    { ...base, id: hex('result:calendar'), kind: 'artifact', direction: 'incoming', state: 'pending', historical_state: 'pending',
      title: 'Result: Calendar sync', context: supper, peer_id: riya.peer_id, parent_id: hex('part:calendar'), created_at: now - 1.2 * hour,
      team: { record: 'result', checks: [{ rule: 'Read only access to the shared calendar', kept: true }, { rule: 'Email guests', kept: true }], compute_used: { micro: 2_400_000, currency: 'GBP' } } },
    { ...base, id: hex('shop'), kind: 'task', direction: 'incoming', state: 'accepted', historical_state: 'accepted',
      title: 'Weekly shop, kept under £60', context: hex('context:shop'), peer_id: riya.peer_id, created_at: now - 2 * hour,
      mission_cap: { cap_micro: 60_000_000, currency: 'GBP' } },
    { ...base, id: hex('cinema'), kind: 'task', direction: 'outgoing', state: 'accepted', historical_state: 'accepted',
      title: 'Find a film for Friday', context: hex('context:friday'), peer_id: sam.peer_id, created_at: now - 50 * hour },
  ];
  const content: Record<string, string> = {
    [hex('lido')]: 'Deposit to The Lido for Sam’s 40th on Saturday 14 March. £120, refundable until 10 March. Tom has already agreed. Otto pays this one deposit and nothing else.',
    [hex('part:menu')]: 'Build the menu page for the supper club app: this week’s dishes, prices and allergens, from the shared menu sheet.\n\nMust: match the Parlu look.\nMust not: add tracking.',
    [hex('result:calendar')]: 'Calendar sync is ready. Bookings appear on the shared supper club calendar within a minute. Read only access, no guest emails. Tests pass.',
  };
  const approvals: Approvals = {
    messages: [{ draft_id: 'msg-thursday', assistant_id: 'Juniper', conversation_id: 'sams-40th',
      text: 'Thursday works for us. 8pm at The Lido, and we’ll bring the cake.', digest: hex('msg-thursday') }],
    questions: [{ question_id: 'q-quotes', question: 'Riya’s quotes land tomorrow. Shall I wait for them before booking the caterer?',
      options: ['Wait for the quotes', 'Book the usual caterer'], state: 'waiting', answer: null, expires_at: now + 20 * hour,
      assistant_id: 'Juniper', conversation_id: 'sams-40th' }],
    drafts: [], drafts_available: true, count: 2,
  };
  const timeline: TimelineEntry[] = [
    { seq: 1, at: now - 50 * hour, conversation_id: 'friday', role: 'owner', kind: 'proposal_sent', ref: null, detail: { summary: 'You asked Bramble, Sam’s assistant, to find a film for Friday' } },
    { seq: 2, at: now - 26 * hour, conversation_id: 'supper-club', role: 'assistant', kind: 'team_started', ref: null, detail: { summary: 'Juniper split the supper club app into three parts' } },
    { seq: 3, at: now - 2 * hour, conversation_id: 'shop', role: 'owner', kind: 'agreed', ref: null, detail: { summary: 'You agreed the weekly shop, kept under £60' } },
    { seq: 4, at: now - 1.2 * hour, conversation_id: 'supper-club', role: 'peer', kind: 'result_arrived', ref: null, detail: { summary: 'Wren, Riya’s assistant, sent back Calendar sync' } },
  ];
  return { identity: { owner_id: 'Maya', agent_id: 'Juniper' }, peers: [tom, riya, kofi, sam], items, content, approvals, timeline, invites: [] };
}

export class DemoBackend implements Backend {
  readonly mode = 'demo' as const;
  readonly address = 'Demo';
  private story: Story;
  private signedIn = false;
  private seq = 100;

  constructor(now = Date.now() / 1000) { this.story = demoStory(now); }

  private log(summary: string, kind = 'decision') {
    this.story.timeline.push({ seq: ++this.seq, at: Date.now() / 1000, conversation_id: null, role: 'owner', kind, ref: null, detail: { summary } });
  }

  private item(id: string) {
    const found = this.story.items.find(entry => entry.id === id);
    if (!found) throw new Error('Not found');
    return found;
  }

  private peerName(id: string) {
    const p = this.story.peers.find(entry => entry.peer_id === id);
    return p ? `${p.agent_id}, ${p.owner_id}’s assistant` : 'their assistant';
  }

  async signIn(password: string) {
    await wait();
    if (!password) throw new Error(`Type any password. The demo password is “${PASSWORD_HINT}”.`);
    this.signedIn = true;
    return this.story.identity;
  }

  async signOut() { this.signedIn = false; }

  async state(): Promise<State> {
    await wait(120);
    const s = this.story;
    return {
      identity: s.identity, peers: s.peers.map(p => ({ ...p })),
      // Saved in the order they were made, as the real owner API returns them.
      items: [...s.items].sort((a, b) => a.created_at - b.created_at).map(i => ({ ...i })),
      relay: { enabled: true, relay_host: 'demo', invites: s.invites.map(i => ({ ...i })), joiners: [], links: [] },
      approvals: { enabled: true },
      demo: true,
    };
  }

  async approvals() {
    await wait(80);
    const a = this.story.approvals;
    const questions = a.questions.filter(q => q.state === 'waiting');
    return { ...a, questions, count: a.messages.length + questions.length + a.drafts.length };
  }

  async review(itemId: string): Promise<Review> {
    await wait(150);
    const item = this.item(itemId);
    const pending = item.state === 'pending', draft = item.state === 'draft';
    return {
      item_id: item.id, context: item.context, artifact_digest: hex('artifact:' + item.id),
      content: this.story.content[item.id] ?? item.title,
      allowed_actions: item.direction === 'incoming' ? (pending ? ['accept', 'reject'] : []) : (draft ? ['release', 'cancel'] : []),
      review_digest: hex('review:' + item.id + item.state),
    };
  }

  async decide(itemId: string, reviewDigest: string, decision: 'accept' | 'reject') {
    await wait();
    const item = this.item(itemId);
    if (reviewDigest !== hex('review:' + item.id + item.state) || item.state !== 'pending') throw new Error('Changed');
    item.state = decision === 'accept' ? 'accepted' : 'rejected';
    item.historical_state = item.state;
    this.log(`You ${decision === 'accept' ? 'agreed to' : 'said no to'} “${item.title}” from ${this.peerName(item.peer_id)}`);
    return { ...item, decision_digest: hex('decision:' + item.id) };
  }

  async release(itemId: string, reviewDigest: string) {
    await wait();
    const item = this.item(itemId);
    if (reviewDigest !== hex('review:' + item.id + item.state) || item.state !== 'draft') throw new Error('Changed');
    item.state = 'pending';
    item.historical_state = 'pending';
    this.log(`You sent “${item.title}” to ${this.peerName(item.peer_id)}`);
    return { state: 'pending' };
  }

  async approveMessage(draftId: string, digest: string) {
    await wait();
    const a = this.story.approvals, found = a.messages.find(m => m.draft_id === draftId);
    if (!found || found.digest !== digest) throw new Error('Changed');
    a.messages = a.messages.filter(m => m !== found);
    this.log(`Juniper sent your message: “${found.text}”`);
    return { sent: true };
  }

  async declineMessage(draftId: string) {
    await wait();
    const a = this.story.approvals;
    a.messages = a.messages.filter(m => m.draft_id !== draftId);
    this.log('You told Juniper not to send a message');
    return { declined: true };
  }

  async answer(questionId: string, option: number) {
    await wait();
    const q = this.story.approvals.questions.find(entry => entry.question_id === questionId);
    if (!q || !Number.isInteger(option) || option < 0 || option >= q.options.length) throw new Error('Unknown');
    q.state = 'answered';
    q.answer = q.options[option];
    this.log(`You answered Juniper: “${q.answer}”`);
    return { state: 'answered', answer: q.answer, authority: 'information-only' };
  }

  async reviewDraft(): Promise<DraftReview> { throw new Error('No shared drafts in the demo'); }
  async approveDraft(): Promise<unknown> { throw new Error('No shared drafts in the demo'); }

  async createInvite(label: string): Promise<InviteMade> {
    await wait();
    const id = hex('invite:' + label + this.story.invites.length).slice(0, 32);
    const code = String(1000 + (parseInt(id.slice(0, 6), 16) % 9000));
    const link = `https://parlu-relay.vercel.app/invite#demo${hex(id)}${hex(id + 'x').slice(0, 20)}`;
    const invite = { id, label: label.trim(), code, created: Date.now() / 1000, join_by: Date.now() / 1000 + 24 * 3600, state: 'open' as const, link };
    this.story.invites.unshift(invite);
    return { made: true, ...invite };
  }

  async openInvite(link: string): Promise<InviteReview> {
    await wait();
    const clean = inviteFromText(link);
    const inviter = { owner_id: 'Ada', agent_id: 'Kestrel', fingerprint: hex('peer:Ada') };
    if (!clean) return { ok: false, inviter, label: '', relay_host: 'demo', reason: 'other_relay' };
    return { ok: true, inviter, label: 'Book club', relay_host: 'parlu-relay.vercel.app', code: '3047', known: false, review_digest: hex('join:' + clean) };
  }

  async acceptInvite(link: string, reviewDigest: string) {
    await wait();
    if (reviewDigest !== hex('join:' + inviteFromText(link))) return { joined: false, reason: 'cannot_add' };
    if (!this.story.peers.some(p => p.owner_id === 'Ada')) this.story.peers.push(peer('Ada', 'Kestrel'));
    this.log('You connected with Ada and Kestrel, Ada’s assistant', 'connected');
    return { joined: true, state: 'waiting' };
  }

  async decideJoiner() { return { decided: false, reason: 'cannot_add' }; }

  async timeline() {
    await wait(100);
    return this.story.timeline.map(entry => ({ ...entry }));
  }
}

export const DEMO_PASSWORD = PASSWORD_HINT;
