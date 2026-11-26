// Recents › Activity in plain words. Each saved event becomes one sentence about what happened,
// using the names people know rather than event codes. Pure, so the view and the tests agree.
// The exact item and its digests stay one tap away in its review.

const cap = value => { const text = String(value ?? '').trim(); return text ? text[0].toUpperCase() + text.slice(1) : ''; };
const quoted = title => `“${String(title ?? '').trim() || 'Untitled'}”`;
const agreed = decision => String(decision ?? '').startsWith('accept');

export function activityLine(event, {items = [], peers = []} = {}) {
  const item = items.find(entry => entry.id === event?.item_id);
  const data = event?.data ?? {};
  const peer = peers.find(entry => entry.peer_id === (item?.peer_id ?? data.peer)) ?? null;
  const owner = cap(peer?.owner_id) || 'The other owner';
  const agent = cap(peer?.agent_id) || 'Their assistant';
  const title = quoted(item?.title);
  const result = item?.kind === 'artifact';
  switch (event?.event) {
    case 'peer_enrolled': return `You connected with ${owner} and ${agent}`;
    case 'peer_revoked': return `You removed ${agent}`;
    case 'proposal_created': return result ? `You prepared the result ${title}` : `You drafted ${title} for ${owner}`;
    case 'proposal_released': return `You sent ${title} to ${agent}`;
    case 'proposal_received':
      if (data.cancelled) return `${agent} sent ${title} and then withdrew it`;
      return result ? `${agent} returned ${title}` : `${agent} asked you: ${title}`;
    case 'recipient_decided': return agreed(data.decision) ? `You agreed to ${title}` : `You turned down ${title}`;
    case 'peer_decision_observed': return agreed(data.decision) ? `${owner} agreed to ${title}` : `${owner} turned down ${title}`;
    case 'cancellation_requested': return `You withdrew ${title}`;
    case 'peer_cancellation_observed': return `${agent} withdrew ${title}`;
    default: {
      const label = String(event?.label ?? event?.event ?? '').replaceAll('_', ' ').trim();
      return cap(label) || 'Saved event';
    }
  }
}

// Whether the line is about the other side (their dot is teal) or you (coral), as in the mock.
export function activityIsYours(event) {
  return ['proposal_created', 'proposal_released', 'recipient_decided', 'cancellation_requested', 'peer_enrolled', 'peer_revoked'].includes(event?.event);
}
