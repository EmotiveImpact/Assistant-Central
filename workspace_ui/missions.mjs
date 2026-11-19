// A mission operates inside the current conversation's session and operation gate.
export function openMissions({dialog, room, principal, name, call, close, node, btn, field, select}) {
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
  function listing() {
    route('list', {}, ({missions}) => {
      const rows = missions.map(m => btn(m.goal + ' · revision ' + m.revision, () => inspect(m.id)));
      section('Mission agreements', ...rows, btn('Create mission agreement', () => edit()));
    });
  }
  function edit(previous) {
    const initial = previous && parse(previous);
    const goal = input(512, initial?.goal), deliverable = input(512, initial?.deliverable);
    const executor = select(room.participants.filter(p => p.principal !== principal).map(p => [p.principal, name(p.principal)]));
    if (initial) executor.value = initial.executor;
    const amount = input(12, String(initial?.cap_microusd ?? 300)); amount.type = 'number'; amount.min = '0'; amount.step = '1';
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
      if (!goal.value.trim() || !deliverable.value.trim() || !executor.value || !amount.value || !amount.checkValidity() || !criteria.length || criteria.some(c=>c.value==='')) {
        message.textContent = 'Enter a goal, deliverable, executor, budget and success check.'; return;
      }
      route('create', {terms:{goal:goal.value, deliverable:deliverable.value, executor:executor.value, cap_microusd:Number(amount.value), criteria},
        expires_at:Math.floor(Date.now()/1000)+1800, request_id:id(), ...(previous ? {replaces:previous.id} : {})}, v => inspect(v.proposal.statement.id), true);
    };
    const message=node('p'); message.setAttribute('role','status');
    section(previous?'Revise mission':'Create mission agreement',field('Goal',goal),field('Deliverable',deliverable),field('Executing owner',executor),
      field('Simulated budget in millionths of a US dollar',amount),list,btn('Add check',()=>{if(list.childElementCount<12)add();}),
      node('p','Valid for 30 minutes. Work pauses for owner decisions and stops at the usage limit or expiry.'),message,btn('Save revision',submit));
  }
  function inspect(pid) {
    route('inspect', {proposal_id:pid}, view => {
      const s = signature(view.proposal), t = parse(s);
      const controls = [];
      if (view.proposal_current) {
        if (!view.current_approval_owners.includes(principal)) controls.push(btn('Review agreement', () => {
          route('review',{proposal_id:pid}, review => {
            const exact = signature(review.proposal);
            section('Approve this revision',node('pre',JSON.stringify(parse(exact),null,2),'artifact-content'),
              node('p','Owners: '+exact.audience.map(a=>name(a.principal)).join(', ')),
              node('p','Revision '+exact.revision+' · expires '+new Date(exact.expires_at*1000).toLocaleString()),
              node('p','Agreement only. Task release, provider use and accepting a return each require a separate decision.'),
              btn('Approve exact revision',()=>route('approve',{proposal_id:pid,review_digest:review.review_digest},()=>inspect(pid),true)));
          });
        }));
        else controls.push(btn('Withdraw my agreement',()=>route('withdraw',{proposal_id:pid,proposal_digest:view.mission_digest},()=>inspect(pid),true)));
        if (s.author===principal) controls.push(btn('Prepare revised terms',()=>edit(s)));
      }
      if (view.all_owners_approved && s.author === principal) {
        const brief=node('textarea'); brief.maxLength=4096;
        controls.push(field('New fictional brief to share with the executing owner and fixture',brief),
          btn('Create task for separate release',()=>{if(brief.value.trim())route('draft',{proposal_id:pid,proposal_digest:view.mission_digest,brief:brief.value,task_id:id()},
            task=>section('Task ready for release',node('p','Open the outbox to review this draft.'),node('code',task.id)),true);}));
        const artifact=input(64);
        controls.push(field('Returned artefact ID',artifact),btn('Check returned artefact',()=>route('evaluate',{proposal_id:pid,artifact_id:artifact.value},
          report=>section('Evidence for the returned artefact',node('pre',JSON.stringify(report,null,2),'artifact-content'),node('p','Review the return in your inbox to accept or reject it.')))));
      }
      section(t.goal,node('p',t.deliverable),node('p','Executor: '+name(t.executor)),
        node('p','Revision '+s.revision+' · '+view.current_approval_owners.length+' of '+s.audience.length+' owners agreed · '+(view.proposal_current?'current':'inactive')),
        node('p','Simulated budget: '+t.cap_microusd+' millionths of a US dollar'),
        ...t.criteria.map(c=>node('p',c.kind+' · '+c.value)),...controls);
    });
  }
  section('Mission agreements',node('p','Loading agreements…'));
  dialog.showModal();
  listing();
}
