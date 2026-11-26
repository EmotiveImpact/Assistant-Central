// Parlu Depth: calm on the surface, deep on demand.
// Glance is Home. Decide is one exact review (a sheet on the phone, a dialog on desktop).
// Inspect is everything else: four places in the sidebar, the Everything list, and a
// side panel that can stay pinned open beside the page on desktop.

// The four places. Every existing screen lives inside one of them, so nothing is lost.
export const SECTIONS = Object.freeze({
  home: {label: 'Home', views: ['overview', 'approvals']},
  recents: {label: 'Recents', views: ['activity', 'receipts', 'tasks', 'inbox', 'artifacts', 'outbox', 'host-drafts'],
    tabs: [['activity', 'Activity'], ['receipts', 'Receipts'], ['tasks', 'All work']]},
  assistants: {label: 'Assistants', views: ['peers', 'conversations', 'transfers'],
    tabs: [['peers', 'Network'], ['conversations', 'Conversations'], ['transfers', 'Connections']]},
  money: {label: 'Money', views: ['money', 'team']},
});

// All work is one tab with filters; each filter is one of the existing screens.
export const WORK_VIEWS = Object.freeze(['tasks', 'inbox', 'artifacts', 'outbox', 'host-drafts']);
export const WORK_FILTERS = Object.freeze([['tasks', 'All'], ['inbox', 'To review'], ['artifacts', 'Results'],
  ['outbox', 'Waiting to send'], ['host-drafts', 'From your apps']]);

export function sectionOf(view) {
  for (const [id, section] of Object.entries(SECTIONS)) if (section.views.includes(view)) return id;
  return 'home';
}

// The tab that stays lit for a view: every work filter belongs to All work.
export function tabOf(view) { return WORK_VIEWS.includes(view) ? 'tasks' : view; }

// Records, newest first: signed owner decisions, and the content hash of each finished run.
// Only digests that exist in saved state are listed. Saved state keeps no time for a decision,
// so the order comes from the saved event sequence: the latest decision or run event for the
// item. Without one, the proposal's own time is used.
export function receiptsOf(state) {
  const receipts = [], history = state?.history ?? [];
  const latest = (itemId, match) => history.reduce((top, event) =>
    event?.item_id === itemId && Number.isSafeInteger(event.sequence) && match(event) ? Math.max(top, event.sequence) : top, 0);
  for (const item of state?.items ?? []) {
    if (item.decision_digest) receipts.push({kind: 'decision', item, digest: item.decision_digest, at: Number(item.created_at) || 0,
      order: latest(item.id, event => /decid|decision/.test(String(event.event)))});
  }
  for (const run of state?.workflow?.runs ?? []) {
    if (!run?.result_digest) continue;
    const item = (state.items ?? []).find(entry => entry.id === run.item_id);
    receipts.push({kind: 'result', item, run, digest: run.result_digest, at: Number(item?.created_at) || 0,
      order: latest(run.item_id, event => String(event.event).startsWith('workflow') || event.data?.run_id === run.run_id)});
  }
  return receipts.sort((a, b) => b.order - a.order || b.at - a.at);
}

export function shortDigest(value) {
  const text = String(value ?? '');
  return text.length > 12 ? text.slice(0, 4) + '…' + text.slice(-4) : text;
}

// The side panel. It never decides anything: it shows a full picture and hands
// decisions to the exact review. Pinned, it stays open as you move between places.
export function createInspect(nodes, {onChange = () => {}} = {}) {
  const {panel, title, sub, body, pin, close, back} = nodes;
  let pinned = false, opener = null, current = null;
  function sync() {
    pin.setAttribute('aria-pressed', String(pinned));
    pin.textContent = pinned ? 'Pinned' : 'Pin open';
    document.body.classList.toggle('inspect-open', !panel.hidden);
    document.body.classList.toggle('inspect-pinned', pinned && !panel.hidden);
    onChange(!panel.hidden);
  }
  function open(key, heading, subtitle, render, {refresh = false} = {}) {
    // A refresh redraws the record that is already open from newer saved state. It never
    // opens or closes the panel, and it leaves the pin alone. Focus stays on the same control
    // when the redraw still has it; otherwise it moves to the panel's title, so the keyboard
    // is never left outside the panel.
    if (refresh) {
      if (panel.hidden || current !== key) return;
      const top = body.scrollTop, held = body.contains(document.activeElement) ? document.activeElement : null;
      title.textContent = heading; sub.textContent = subtitle || '';
      body.replaceChildren(); render(body); body.scrollTop = top;
      if (held) {
        const same = [...body.querySelectorAll('button,a[href],input,select,textarea')]
          .find(node => node.tagName === held.tagName && node.textContent === held.textContent);
        title.tabIndex = -1;
        (same ?? title).focus({preventScroll: true});
      }
      return;
    }
    if (!panel.hidden && current === key && !pinned) { hide(); return; }
    // A record opened from inside the open panel replaces it, and the line that was pressed is
    // about to be removed. The first launcher is kept, so closing still returns the keyboard
    // to where the owner started.
    const active = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (panel.hidden || !panel.contains(active)) opener = active;
    current = key;
    title.textContent = heading;
    sub.textContent = subtitle || '';
    body.replaceChildren();
    render(body);
    panel.hidden = false;
    sync();
    title.tabIndex = -1;
    title.focus({preventScroll: true});
  }
  function hide({restoreFocus = true} = {}) {
    if (panel.hidden) return;
    panel.hidden = true;
    current = null;
    // Nothing from the closed record stays in the page, so a locked workspace keeps no trace of it.
    body.replaceChildren(); title.textContent = ''; sub.textContent = '';
    sync();
    if (restoreFocus && opener?.isConnected) opener.focus({preventScroll: true});
    opener = null;
  }
  pin.addEventListener('click', () => { pinned = !pinned; sync(); });
  close.addEventListener('click', () => hide());
  back?.addEventListener('click', () => hide());
  panel.addEventListener('keydown', event => { if (event.key === 'Escape') { event.stopPropagation(); hide(); } });
  return {
    open, hide,
    get pinned() { return pinned; },
    get current() { return current; },
    // Moving to another place closes an unpinned panel.
    navigated() { if (!pinned) hide({restoreFocus: false}); },
    reset() { pinned = false; hide({restoreFocus: false}); sync(); },
  };
}
