// What Home says, worked out from saved state only. The words follow the desktop's Home
// exactly (same queue, same closing line), laid out for a phone: a short paragraph with the
// asking pair inline, then one card at a time.
import type { Approvals, Item, Peer, State } from './types';
import {
  CARD, askerOf, attentionItems, closingLine, doneToday, eveningSummary, homeGreeting, homeQueue, isEvening,
  joinerCards, moreLine, partLead, partOf, uncheckedParts,
} from '../shared/web';

export type Entry = {
  kind: 'proposal' | 'question' | 'message' | 'shared-draft' | 'invite' | 'joiner' | 'host-draft';
  key: string;
  title: string;
  item?: Item;
  joiner?: NonNullable<State['relay']>['joiners'][number];
  view?: string;
  owner?: string;
  agent?: string;
};

export type Segment = { text: string; bold?: boolean } | { pair: { owner: string; agent: string } };

export type Card = {
  entry: Entry;
  owner: string;
  agent: string;
  yours: boolean;
  who: string;
  lead: string;
  team: string;
  action: string;
};

const cap = (value: string) => value ? value.charAt(0).toUpperCase() + value.slice(1) : value;

export function peerOf(state: State, item?: Item): Peer | undefined {
  return item ? state.peers.find(peer => peer.peer_id === item.peer_id) : undefined;
}

export function queueOf(state: State, approvals: Approvals | null): Entry[] {
  return homeQueue({ proposals: attentionItems(state), approvals, joiners: joinerCards(state) }) as Entry[];
}

export function failedParts(approvals: Approvals | null, approvalsFailed = false): string[] {
  const parts = uncheckedParts({ approvals }) as string[];
  return approvalsFailed ? ['your assistant’s questions', ...parts] : parts;
}

export function cardFor(state: State, entry: Entry): Card {
  const me = cap(state.identity.owner_id || 'You'), mine = state.identity.agent_id || 'Your assistant';
  const ask = askerOf(entry, { me, mine, peer: peerOf(state, entry.item) }) as { owner: string; agent: string; yours: boolean };
  const owner = cap(ask.owner || 'Someone'), agent = ask.agent || 'Their assistant';
  const copy = (CARD as Record<string, { lead: string; action: string }>)[entry.kind];
  const lead = !copy.lead ? '' : copy.lead[0] === copy.lead[0].toUpperCase() ? copy.lead : `${agent} ${copy.lead}`;
  const team = entry.kind === 'proposal' ? partLead(partOf(state, entry.item)) as string : '';
  return { entry, owner, agent, yours: ask.yours, who: ask.yours ? `${agent}, your assistant` : `${agent}, ${owner}’s assistant`, lead, team, action: copy.action };
}

/** The paragraph at the top of Home: at most three sentences, ending with an honest line. */
export function paragraph(state: State, queue: Entry[], failed: string[], hour: number, offset = 0): Segment[] {
  const me = cap(state.identity.owner_id || 'there');
  const out: Segment[] = [{ text: `${homeGreeting(hour)} ${me}. ` }];
  const n = queue.length, done = doneToday(state.items) as Item[];
  if (!n) {
    if (isEvening(hour) && done.length) out.push({ text: eveningSummary(done, (item: Item) => peerOf(state, item)) + ' ' });
    out.push({ text: failed.length ? closingLine(failed) : 'Nothing needs you right now.', bold: true });
    return out;
  }
  const first = queue[offset % n], c = cardFor(state, first), pair = { pair: { owner: c.owner, agent: c.agent } };
  if (n === 1) out[0] = { text: `${homeGreeting(hour)} ${me}. Just one thing. ` };
  switch (first.kind) {
    case 'proposal': out.push({ text: `${c.owner}’s ` }, pair, { text: ` ${c.agent} sent ` }, { text: first.title, bold: true }); break;
    case 'question': out.push({ text: 'Your ' }, pair, { text: ` ${c.agent} asked you ` }, { text: `“${first.title}”`, bold: true }); break;
    case 'message': out.push({ text: 'Your ' }, pair, { text: ` ${c.agent} ` }, { text: 'wants to send a message for you', bold: true }); break;
    case 'invite': out.push({ text: `${c.owner}’s ` }, pair, { text: ` ${c.agent} ` }, { text: 'invited you to a conversation', bold: true }); break;
    case 'joiner': out.push({ text: `${c.owner} and ` }, pair, { text: ` ${c.agent} ` }, { text: 'used your invite and ask to connect', bold: true }); break;
    case 'shared-draft': out.push({ text: 'A shared draft waits for your agreement', bold: true }); break;
    default: out.push({ text: 'A draft from one of your apps, ' }, { text: `“${first.title}”`, bold: true }, { text: ',' });
  }
  out.push({ text: moreLine(n) }, { text: closingLine(failed), bold: true });
  return out;
}

/** The cards in view, the first one live, in the order Not now cycles through. */
export function cardStack(state: State, queue: Entry[], offset = 0, depth = 3): Card[] {
  const n = queue.length;
  if (!n) return [];
  const start = offset % n;
  return queue.slice(start).concat(queue.slice(0, start)).slice(0, depth).map(entry => cardFor(state, entry));
}

export function plainText(segments: Segment[]): string {
  return segments.map(s => 'pair' in s ? `${s.pair.owner} and ${s.pair.agent}` : s.text).join('');
}
