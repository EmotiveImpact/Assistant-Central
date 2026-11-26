// A mission operates inside the current conversation's session and operation gate.

// Budgets are stored exactly, in millionths of a US dollar. People read and type dollars.
export function dollars(microusd) {
  const value = Number(microusd) / 1e6;
  const digits = value !== 0 && Math.abs(value) < 0.01 ? Math.min(6, Math.max(2, 1 - Math.floor(Math.log10(Math.abs(value))))) : 2;
  return new Intl.NumberFormat('en-GB', {style: 'currency', currency: 'USD', minimumFractionDigits: 2,
    maximumFractionDigits: digits}).format(value);
}

export function toMicro(text) {
  if (!/^\d{1,6}(\.\d{1,6})?$/.test(String(text).trim())) return null;
  return Math.round(Number(text) * 1e6);
}

// One plain sentence per term, for the person deciding. The exact terms stay one click away.
export function describeCheck(c) {
  if (c.kind === 'contains') return `The result must include the words "${c.value}".`;
  if (c.kind === 'max_utf8_bytes') return `The result must be no longer than ${Number(c.value).toLocaleString('en-GB')} bytes.`;
  if (c.kind === 'sha256') return 'The result must exactly match the file you were given a fingerprint for.';
  return `You decide whether it is good enough: ${c.value}`;
}

export function missionSummary(terms, name) {
  return [
    ['What it is for', terms.goal],
    ['What comes back', terms.deliverable],
    ['Who does the work', name(terms.executor)],
    ['Spending limit', dollars(terms.cap_microusd) + ' (simulated, not real money yet)'],
    ['How the result is checked', terms.criteria.map(describeCheck).join(' ')],
  ];
}

export function openMissions({dialog, room, principal, name, call, close, node, btn, field, select, items}) {
  const route = (action, body, show, write = false) => call(action, body, value => {
    if (dialog.open) show(value);
  }, write);
  const section = (title, ...children) => {
    const heading = node('header','','dialog-header'), body = node('div','','dialog-body form-grid');
    heading.append(node('h2', title), btn('Close', close));
    for (const child of children) { child.classList.add('full'); body.append(child); }
    dialog.replaceChildren(heading, body);
  };
  const input = (max, value = '') => {
    const e = node('input'); e.maxLength = max; e.value = value; return e;
  };
  const id = () => crypto.randomUUID().replaceAll('-', '');
  const signature = proposal => proposal.statement;
  const parse = statement => {
    const record = JSON.parse(statement.content);
    if (record.domain !== 'assistant-central/mission-agreement/1' || statement.conversation_id !== room.id)
      throw new Error('Unexpected mission agreement');
    return record.terms;
  };
  function summaryRows(terms) {
    const list = node('dl','','mission-summary');
    for (const [label, value] of missionSummary(terms, name)) list.append(node('dt', label), node('dd', value));
    return [list];
  }
  function listing() {
    route('list', {}, ({missions}) => {
      const rows = missions.map(m => btn(m.goal + ' · revision ' + m.revision, () => inspect(m.id)));
      section('Mission agreements', ...rows, btn('Create mission agreement', () => edit(), 'primary'));
    });
  }
  function edit(previous) {
    const initial = previous && parse(previous);
    const goal = input(512, initial?.goal), deliverable = input(512, initial?.deliverable);
    const executor = select(room.participants.filter(p => p.principal !== principal).map(p => [p.principal, name(p.principal)]));
    if (initial) executor.value = initial.executor;
    const amount = input(14, initial ? String(initial.cap_microusd / 1e6) : '0.0003'); amount.inputMode = 'decimal';
    const list = node('div'), rules = [];
    function add(rule = {kind:'contains', value:''}) {
      const kind = select([['contains','Contains text'],['max_utf8_bytes','Maximum UTF-8 bytes'],['sha256','Exact SHA-256'],['human_review','Owner judgement']]);
      kind.value = rule.kind;
      const value = input(256, String(rule.value)), row = node('div');
      row.append(field('Check', kind), field('Expected value', value), btn('Remove check', () => {row.remove();}));
      list.append(row); rules.push({row, kind, value});
    }
    (initial?.criteria ?? [undefined]).forEach(add);
    const submit = () => {
      const criteria = rules.filter(r => list.contains(r.row)).map(({kind,value}) => ({kind:kind.value, value:kind.value === 'max_utf8_bytes' ? Number(value.value) : value.value}));
      const cap = toMicro(amount.value);
      if (!goal.value.trim() || !deliverable.value.trim() || !executor.value || cap === null || !criteria.length || criteria.some(c=>c.value==='')) {
        message.textContent = 'Enter a goal, deliverable, executor, a spending limit in dollars (such as 0.50) and a success check.'; return;
      }
      route('create', {terms:{goal:goal.value, deliverable:deliverable.value, executor:executor.value, cap_microusd:cap, criteria},
        expires_at:Math.floor(Date.now()/1000)+1800, request_id:id(), ...(previous ? {replaces:previous.id} : {})}, v => inspect(v.proposal.statement.id), true);
    };
    const message=node('p'); message.setAttribute('role','status');
    section(previous?'Revise mission':'Create mission agreement',field('Goal',goal),field('Deliverable',deliverable),field('Executing owner',executor),
      field('Spending limit in US dollars (simulated)',amount),list,btn('Add check',()=>{if(list.childElementCount<12)add();}),
      node('p','Valid for 30 minutes. Work pauses for owner decisions and stops at the usage limit or expiry.'),message,btn('Save revision',submit,'primary'));
  }
  function inspect(pid) {
    route('inspect', {proposal_id:pid}, view => {
      const s = signature(view.proposal), t = parse(s);
      const controls = [];
      if (view.proposal_current) {
        const withdrawn=view.revocations.some(r=>r.statement.owner===principal);
        if(withdrawn)controls.push(node('p','You withdrew agreement to this revision. A new revision requires fresh approval.'));
        else if (!view.current_approval_owners.includes(principal)) controls.push(btn('Review agreement', () => {
          route('review',{proposal_id:pid}, review => {
            const exact = signature(review.proposal);
            const details = node('details'), terms = parse(exact);
            details.append(node('summary','Show the exact terms'), node('pre',JSON.stringify(terms,null,2),'artifact-content'));
            section('Approve this revision',...summaryRows(terms),details,
              node('p','Owners: '+exact.audience.map(a=>name(a.principal)).join(', ')),
              node('p','Revision '+exact.revision+' · expires '+new Date(exact.expires_at*1000).toLocaleString()),
              node('p','Agreement only. Task release, provider use and accepting a return each require a separate decision.'),
              btn('Approve exact revision',()=>route('approve',{proposal_id:pid,review_digest:review.review_digest},()=>inspect(pid),true),'primary'));
          });
        }, 'primary'));
        else controls.push(btn('Withdraw my agreement',()=>route('withdraw',{proposal_id:pid,proposal_digest:view.mission_digest},()=>inspect(pid),true)));
        if (s.author===principal) controls.push(btn('Prepare revised terms',()=>edit(s)));
      }
      if (view.all_owners_approved && s.author === principal) {
        const brief=node('textarea'); brief.maxLength=4096;
        controls.push(field('New fictional brief to share with the executing owner and fixture',brief),
          btn('Create task for separate release',()=>{if(brief.value.trim())route('draft',{proposal_id:pid,proposal_digest:view.mission_digest,brief:brief.value,task_id:id()},
            task=>section('Task ready for release',node('p','Open the outbox to review this draft.'),node('code',task.id)),true);}));
        const returns=items().filter(item=>item.context===view.task_context && item.direction==='incoming' && item.kind==='artifact' && ['pending','accepted'].includes(item.state));
        const artifact=select(returns.map(item=>[item.id,item.title+' · '+item.id.slice(0,12)]));
        if(returns.length) controls.push(field('Returned artefact',artifact),btn('Check returned artefact',()=>route('evaluate',{proposal_id:pid,artifact_id:artifact.value},
          report=>section('Evidence for the returned artefact',node('pre',JSON.stringify(report,null,2),'artifact-content'),node('p','Review the return in your inbox to accept or reject it.')))));
      }
      section(t.goal,...summaryRows(t),
        node('p','Revision '+s.revision+' · '+view.current_approval_owners.length+' of '+s.audience.length+' owners agreed · '+(view.proposal_current?'current':'inactive')),
        ...controls);
    });
  }
  section('Mission agreements',node('p','Loading agreements…'));
  dialog.showModal();
  listing();
}
