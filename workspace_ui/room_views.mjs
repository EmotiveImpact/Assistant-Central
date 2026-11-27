// Rooms, the board and canvas, the timeline and groups, drawn from saved state.
// Nothing here decides anything: every yes, no and send opens the exact review of one signed
// record. Positions on the canvas are a view preference kept in this browser only.
import {ownerPair} from './bots.mjs';
import {COLUMNS,NOTE_WORDS,RULE_WORDS,TIMELINE_FILTERS,roomsOf,roomLine,columnOf,filterTimeline,eventLine,groupsOf,canvasLayout} from './rooms.mjs';

const calm=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
function el(tag,className,value){const node=document.createElement(tag);if(className)node.className=className;if(value!==undefined&&value!==null)node.textContent=String(value);return node;}
function btn(label,className,handler){const node=el('button',className,label);node.type='button';node.addEventListener('click',handler);return node;}
const cap=value=>{const text=String(value??'').trim();return text?text[0].toUpperCase()+text.slice(1):'';};
const clip=(value,max)=>{const text=String(value??'').replace(/\s+/g,' ').trim();return text.length>max?text.slice(0,max-1)+'…':text;};
function timeOf(seconds){
  const n=Number(seconds);if(!Number.isFinite(n)||n<=0)return '';
  return new Date(n*1000).toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit'});
}
function dayOf(seconds){
  const n=Number(seconds);if(!Number.isFinite(n)||n<=0)return '';
  const date=new Date(n*1000),today=new Date();
  if(date.toDateString()===today.toDateString())return 'Today';
  return date.toLocaleDateString('en-GB',{weekday:'long',day:'numeric',month:'long'});
}
function store(key,value){try{if(value===undefined)return JSON.parse(localStorage.getItem(key)??'null');localStorage.setItem(key,JSON.stringify(value));}catch{return null;}return value;}

export function createRoomViews(ctx){
  // ctx: state(), peer(id), openRoom(context,tab), openReview(item), showPanel(key,heading,sub,draw,again), openRoomDialog(mode,room), navigate(view)
  let roomTab='threads',threadFilter='all',boardMode=store('parlu.boardMode')==='canvas'?'canvas':'columns',timelineFilter='all';
  const me=()=>ctx.state().identity;
  function person(who){
    if(who==='you')return {owner:cap(me().owner_id)||'You',agent:me().agent_id||'Your assistant',you:true};
    const peer=ctx.peer(who);return {owner:cap(peer?.owner_id)||'Someone',agent:peer?.agent_id||'Their assistant',you:false};
  }
  const agentName=who=>who==='you'?`Your ${person('you').agent}`:who==='room'?'The room':person(who).agent;
  const sentenceName=who=>who==='you'?'You':who==='room'?'The room':person(who).agent;
  function pair(who,expression='idle',className='owner-pair'){const p=person(who);return ownerPair(p.owner,p.agent,className,expression);}
  function whoLabel(who){
    const p=person(who),box=el('span','who-label');
    box.append(el('strong','',p.you?`${p.agent}`:p.agent),el('span','',p.you?'your assistant':`${p.owner}'s assistant`));return box;
  }
  // The fictional demo marks its records "SYNTHETIC ONLY"; the footer already says so, so the
  // marker is left out of the reading view. The exact review still shows every word.
  const plainWords=value=>String(value??'').replace(/^SYNTHETIC ONLY[.:]?\s*/i,'');
  function entryTitle(entry){
    if(entry.type==='note')return plainWords(entry.note.summary);
    if(entry.type==='vote')return plainWords(entry.vote.question);
    const title=String(entry.title??''),lead=entry.roomName?entry.roomName+': ':'';
    return lead&&title.startsWith(lead)?title.slice(lead.length):title;
  }
  function entryChip(entry){
    if(entry.type==='note'){const chip=el('span','room-chip note-'+entry.note.note,NOTE_WORDS[entry.note.note]);return chip;}
    if(entry.type==='vote')return el('span','room-chip vote','Vote');
    return el('span','room-chip task',entry.item.kind==='task'&&entry.item.team?.record==='part'?'Part':'Ask');
  }
  function stamp(entry){const time=timeOf(entry.at);return time?el('time','room-time',time):el('span');}
  function needsYou(entry){return columnOf(entry)==='yes';}
  function firstItem(entry){
    if(entry.type==='vote'&&!entry.incoming)return entry.items.find(item=>item.state==='draft')??entry.items[0];
    if(entry.type==='note')return entry.items.find(item=>item.state==='draft')??entry.items[0];
    if(entry.type==='task'){const waiting=entry.results.find(result=>result.state==='pending');return waiting??entry.item;}
    return entry.items[0];
  }
  function actionWords(entry){
    const item=firstItem(entry);
    if(item.state==='draft')return 'Review and send';
    if(entry.type==='vote'&&entry.incoming&&item.state==='pending')return 'Review and vote';
    if(item.direction==='incoming'&&item.state==='pending')return entry.type==='task'&&item.kind==='artifact'?'Review the result':'Review and agree';
    return 'Open the signed record';
  }

  // ===== Tally =====
  function tallyBar(entry){
    const box=el('div','tally');
    if(entry.incoming){
      const line=el('p','tally-line');
      const stance=entry.vote.stance==='yes'?'says yes':entry.vote.stance==='no'?'says no':'has not said';
      line.textContent=`${person(entry.who).agent} ${stance}. ${entry.mine==='yes'?'You voted yes.':entry.mine==='no'?'You voted no.':entry.mine==='none'?'This vote closed before you answered.':'Your answer goes back to them, signed by you.'}`;
      box.append(line);return box;
    }
    const r=entry.result,track=el('div','tally-track');track.setAttribute('role','img');track.setAttribute('aria-label',`${r.yes} yes, ${r.no} no, ${r.open} waiting, of ${r.total}`);
    const yes=el('span','tally-yes'),no=el('span','tally-no');
    yes.style.setProperty('--share',`${(r.yes/r.total)*100}%`);no.style.setProperty('--share',`${(r.no/r.total)*100}%`);
    track.append(yes,no);
    const need=entry.vote.rule==='all'?r.total:Math.floor(r.total/2)+1;
    const mark=el('span','tally-need');mark.style.setProperty('--at',`${(need/r.total)*100}%`);track.append(mark);
    const words=el('p','tally-line');
    words.textContent=r.outcome==='passed'?`Passed. ${r.yes} of ${r.total} said yes. ${RULE_WORDS[entry.vote.rule]} had to agree.`
      :r.outcome==='failed'?`Did not pass. ${r.yes} of ${r.total} said yes. ${RULE_WORDS[entry.vote.rule]} had to agree.`
      :`${r.yes} of ${r.total} yes so far. ${RULE_WORDS[entry.vote.rule]} must agree, so it needs ${need}.`;
    const voters=el('div','voters');
    voters.append(voter('you',entry.vote.stance==='abstain'?'none':entry.vote.stance));
    for(const answer of entry.answers)voters.append(voter(answer.who,answer.answer));
    box.append(track,words,voters);box.dataset.outcome=r.outcome;return box;
  }
  function voter(who,answer){
    const chip=el('span','voter answer-'+answer);chip.append(pair(who,answer==='yes'?'done':answer==='waiting'?'busy':'idle','owner-pair tiny'));
    chip.append(el('span','',`${sentenceName(who)} · ${{yes:'yes',no:'no',waiting:'thinking',unsent:'not sent yet',none:'no answer'}[answer]??answer}`));return chip;
  }

  // ===== Entry panel =====
  function openEntry(room,entry){
    const again=()=>{const fresh=findRoom(room.context);const match=fresh&&fresh.entries.find(other=>firstItem(other).id===firstItem(entry).id);if(match)openEntry(fresh,match);};
    const heading=entry.type==='vote'?'Vote':entry.type==='note'?NOTE_WORDS[entry.note.note]:entry.item.team?.record==='part'?'Part':'Ask';
    ctx.showPanel('room-entry:'+firstItem(entry).id,heading,`${room.name} · ${entry.thread}`,body=>{
      const head=el('div','entry-head');head.append(pair(entry.who,'look'),whoLabel(entry.who));body.append(head);
      body.append(el('p','entry-text',entryTitle(entry)));
      if(entry.type==='note'&&entry.replaces){
        const was=el('div','entry-change');was.append(el('span','entry-label','Before'),el('p','was',plainWords(entry.replaces.note.summary)),el('span','entry-label','Why it changed'),el('p','',entry.note.why??'No reason given.'));body.append(was);
      }else if(entry.type==='note'&&entry.note.why)body.append(el('p','entry-why',entry.note.why));
      if(entry.type==='note'&&entry.replacedBy){const later=el('div','entry-change');later.append(el('span','entry-label','Later replaced by'),el('p','',plainWords(entry.replacedBy.note.summary)));body.append(later);}
      if(entry.type==='vote'){if(entry.vote.why)body.append(el('p','entry-why',entry.vote.why));body.append(tallyBar(entry));}
      if(entry.type==='task'&&entry.results.length){const box=el('div','entry-change');box.append(el('span','entry-label','Results'));for(const result of entry.results)box.append(el('p','',`${result.title} · ${result.historical_state==='accepted'?'accepted':result.state==='pending'?'waiting for you':result.state}`));body.append(box);}
      const facts=el('dl','entry-facts');
      const fact=(label,value)=>{facts.append(el('dt','',label),el('dd','',value));};
      fact('Room',room.name);fact('Thread',entry.thread);
      if(entry.type==='note')fact('On the board',{researching:'Researching',doing:'Doing',done:'Done'}[entry.note.stage]);
      if(entry.type==='vote')fact('Rule',RULE_WORDS[entry.vote.rule]);
      fact('Sent',entry.items.length>1?`To ${entry.items.length} assistants, one signed copy each`:entry.items[0].direction==='outgoing'?`To ${person(entry.items[0].peer_id).agent}`:'To you');
      if(timeOf(entry.at))fact('At',timeOf(entry.at));
      body.append(facts);
      const action=btn(actionWords(entry),needsYou(entry)?'button primary':'button secondary',()=>ctx.openReview(firstItem(entry)));
      body.append(action);
      body.append(el('p','entry-note','Written by that person’s own assistant and signed. Parlu carried it and checked its shape; it did not write it.'));
    },again);
  }

  // ===== Rooms list =====
  function findRoom(context){return roomsOf(ctx.state()).find(room=>room.context===context)??null;}
  function membersStrip(room,limit=5){
    const box=el('span','member-strip');
    box.append(pair('you','idle','owner-pair small'));
    for(const id of room.members.slice(0,limit-1))box.append(pair(id,'idle','owner-pair small'));
    if(room.members.length>limit-1)box.append(el('span','member-more',`+${room.members.length-limit+1}`));
    return box;
  }
  function glyph(room,className='room-glyph'){const g=el('span',className,room.name.trim().slice(0,1).toUpperCase());g.style.setProperty('--tint',room.tint);g.setAttribute('aria-hidden','true');return g;}
  function renderRooms(target){
    const rooms=roomsOf(ctx.state());
    const top=el('div','rooms-top');
    top.append(btn('Start a room','button primary',()=>ctx.openRoomDialog('room',null)));
    target.append(top);
    if(!rooms.length){
      const empty=el('div','empty-state');empty.append(el('h3','','No rooms yet'),el('p','','Start one, or ask two assistants to work on something together.'));target.append(empty);return;
    }
    const list=el('div','rooms-list');
    rooms.forEach((room,index)=>{
      const row=el('button','room-row');row.type='button';row.style.setProperty('--i',index);
      row.addEventListener('click',()=>ctx.openRoom(room.context));
      const main=el('span','room-row-main');main.append(glyph(room));
      const words=el('span','room-row-words');words.append(el('strong','',room.name),el('span','',roomLine(room)));main.append(words);
      const side=el('span','room-row-side');
      const progress=el('span','room-progress');progress.style.setProperty('--share',`${room.total?Math.round(room.done/room.total*100):0}%`);progress.setAttribute('aria-hidden','true');
      side.append(membersStrip(room),progress);
      if(room.needsYou)side.append(el('span','nav-count needs',room.needsYou));
      row.append(main,side);
      row.setAttribute('aria-label',`${room.name}. ${roomLine(room)}`);
      list.append(row);
    });
    target.append(list);
  }

  // ===== One room =====
  function renderRoom(target,context){
    const room=findRoom(context);
    if(!room){const empty=el('div','empty-state');empty.append(el('h3','','This room is not in your saved work'),el('p','','It may have been removed with an assistant.'));empty.append(btn('All rooms','button secondary',()=>ctx.navigate('rooms')));target.append(empty);return null;}
    const bar=el('div','room-bar');
    const crowd=el('div','room-crowd');crowd.append(membersStrip(room,8));
    crowd.append(el('span','room-crowd-words',`You and ${room.members.length===1?person(room.members[0]).owner:`${room.members.length} others`}, each with their own assistant`));
    const actions=el('div','room-actions');
    actions.append(btn('Post a note','button secondary',()=>ctx.openRoomDialog('note',room)),btn('Ask for a vote','button primary',()=>ctx.openRoomDialog('vote',room)));
    bar.append(crowd,actions);target.append(bar);

    const tabs=el('div','room-tabs');tabs.setAttribute('role','tablist');tabs.setAttribute('aria-label','Room');
    const indicator=el('span','room-tab-indicator');tabs.append(indicator);
    const panes={threads:['Threads',room.entries.length],board:['Board',room.total],timeline:['Timeline',room.timeline.length]};
    const pane=el('div','room-pane');
    for(const [id,[label,count]] of Object.entries(panes)){
      const tab=el('button','room-tab'+(roomTab===id?' selected':''));tab.type='button';tab.setAttribute('role','tab');tab.setAttribute('aria-selected',String(roomTab===id));tab.dataset.tab=id;
      tab.append(el('span','',label),el('span','room-tab-count',count));
      tab.addEventListener('click',()=>{if(roomTab===id)return;roomTab=id;ctx.rerender();});
      tabs.append(tab);
    }
    target.append(tabs,pane);
    requestAnimationFrame(()=>{const on=tabs.querySelector('.room-tab.selected');if(on){indicator.style.width=on.offsetWidth+'px';indicator.style.transform=`translateX(${on.offsetLeft}px)`;}});
    if(roomTab==='threads')renderThreads(pane,room);else if(roomTab==='board')renderBoard(pane,room);else renderTimeline(pane,room);
    return room;
  }
  function setTab(tab){if(['threads','board','timeline'].includes(tab))roomTab=tab;}

  // Threads: the conversation, one post per note, vote or ask, filtered by thread.
  function renderThreads(pane,room){
    const layout=el('div','threads-layout');
    const side=el('nav','thread-list');side.setAttribute('aria-label','Threads');
    const filters=[['all','All threads',room.entries.length],...room.threads.map(name=>[name,name,room.entries.filter(entry=>entry.thread===name).length])];
    if(threadFilter!=='all'&&!room.threads.includes(threadFilter))threadFilter='all';
    for(const [id,label,count] of filters){
      const item=el('button','thread-link'+(threadFilter===id?' selected':''));item.type='button';item.append(el('span','',id==='all'?label:'# '+label),el('span','nav-count',count));
      item.setAttribute('aria-pressed',String(threadFilter===id));
      item.addEventListener('click',()=>{threadFilter=id;ctx.rerender();});side.append(item);
    }
    const stream=el('div','thread-stream');
    const shown=room.entries.filter(entry=>threadFilter==='all'||entry.thread===threadFilter);
    let lastDay='';
    shown.forEach((entry,index)=>{
      const day=dayOf(entry.at);if(day&&day!==lastDay){lastDay=day;stream.append(el('div','stream-day',day));}
      stream.append(post(room,entry,index));
    });
    if(!shown.length)stream.append(el('p','quiet-line','Nothing in this thread yet.'));
    layout.append(side,stream);pane.append(layout);
  }
  function post(room,entry,index){
    const card=el('article','room-post'+(needsYou(entry)?' needs-you':'')+(entry.replacedBy?' replaced':''));card.style.setProperty('--i',Math.min(index,12));
    card.dataset.type=entry.type;
    const head=el('div','post-head');head.append(pair(entry.who,entry.type==='vote'?'look':'idle'),whoLabel(entry.who),entryChip(entry));
    if(threadFilter==='all')head.append(el('span','post-thread','# '+entry.thread));
    head.append(stamp(entry));card.append(head);
    if(entry.type==='note'&&entry.replaces){
      const change=el('div','post-change');change.append(el('s','',clip(plainWords(entry.replaces.note.summary),140)),el('span','post-arrow','→'));card.append(change);
    }
    card.append(el('p','post-text',entryTitle(entry)));
    if(entry.type==='note'&&entry.note.why)card.append(el('p','post-why',(entry.note.note==='change'?'Why: ':'')+entry.note.why));
    if(entry.type==='note'&&entry.replacedBy)card.append(el('p','post-why','Replaced later in this room.'));
    if(entry.type==='vote')card.append(tallyBar(entry));
    if(entry.type==='task'){
      const line=entry.results.length?`${entry.results.length} result${entry.results.length===1?'':'s'} returned`:entry.item.state==='draft'?'Ready for you to send':entry.item.historical_state==='accepted'?'Agreed':entry.item.state==='pending'?'Waiting for an answer':cap(entry.item.state);
      card.append(el('p','post-why',line));
    }
    const foot=el('div','post-foot');
    if(needsYou(entry))foot.append(btn(actionWords(entry),'button primary small',()=>ctx.openReview(firstItem(entry))));
    foot.append(btn('Details','text-button',()=>openEntry(room,entry)));
    card.append(foot);
    return card;
  }

  // Board: four columns, or a free canvas of sticky notes, one colour per assistant.
  function renderBoard(pane,room){
    const tools=el('div','board-tools');
    const toggle=el('div','segmented board-mode');toggle.setAttribute('aria-label','Board layout');
    for(const [id,label] of [['columns','Columns'],['canvas','Canvas']]){
      const b=btn(label,boardMode===id?'selected':'',()=>{boardMode=id;store('parlu.boardMode',id);ctx.rerender();});b.setAttribute('aria-pressed',String(boardMode===id));toggle.append(b);
    }
    tools.append(toggle,el('span','board-hint',boardMode==='canvas'?'Drag notes to arrange them. Drag the background to move around. Your layout stays in this browser.':'Each card is one signed note, vote or ask. Open one to see who said what.'));
    pane.append(tools);
    if(boardMode==='canvas'){renderCanvas(pane,room);return;}
    const board=el('div','room-board');
    for(const [id,label] of COLUMNS){
      const col=el('section','board-col col-'+id);col.setAttribute('aria-label',label);
      const head=el('header','board-col-head');head.append(el('span','col-dot'),el('h3','',label),el('span','nav-count',room.board[id].length));col.append(head);
      const cards=el('div','board-cards');
      room.board[id].forEach((entry,index)=>cards.append(boardCard(room,entry,index)));
      if(!room.board[id].length)cards.append(el('p','board-none',id==='yes'?'Nothing needs you here.':'Nothing yet.'));
      col.append(cards);board.append(col);
    }
    pane.append(board);
  }
  function boardCard(room,entry,index){
    const card=el('button','board-card');card.type='button';card.style.setProperty('--i',Math.min(index,10));card.dataset.type=entry.type;
    card.addEventListener('click',()=>openEntry(room,entry));
    const head=el('span','board-card-head');head.append(entryChip(entry),el('span','post-thread','# '+entry.thread));card.append(head);
    card.append(el('span','board-card-title',clip(entryTitle(entry),140)));
    if(entry.type==='note'&&entry.replaces)card.append(el('span','board-card-was','Was: '+clip(plainWords(entry.replaces.note.summary),70)));
    if(entry.type==='vote'&&!entry.incoming){const r=entry.result;const mini=el('span','mini-tally');for(let i=0;i<r.total;i++)mini.append(el('i',i<r.yes?'y':i<r.yes+r.no?'n':''));card.append(mini);}
    const foot=el('span','board-card-foot');foot.append(pair(entry.who,'idle','owner-pair tiny'),el('span','',agentName(entry.who)),stamp(entry));card.append(foot);
    card.setAttribute('aria-label',`${entry.type==='vote'?'Vote':entry.type==='note'?NOTE_WORDS[entry.note.note]:'Ask'} from ${agentName(entry.who)}: ${entryTitle(entry)}`);
    return card;
  }

  function renderCanvas(pane,room){
    const key='parlu.canvas.'+room.context.slice(0,24);
    const saved=store(key)??{};const view={x:saved.x??0,y:saved.y??0,k:saved.k??1};const moved=saved.moved??{};
    const layout=canvasLayout(room);
    const frame=el('div','canvas-frame');frame.tabIndex=0;frame.setAttribute('aria-label','Canvas of the room’s notes. Use the buttons to zoom.');
    const world=el('div','canvas-world');const lines=document.createElementNS('http://www.w3.org/2000/svg','svg');lines.setAttribute('class','canvas-lines');lines.setAttribute('aria-hidden','true');
    world.append(lines);
    const keyOf=entry=>firstItem(entry).id;
    const nodes=new Map();
    layout.lanes.forEach((who,lane)=>{
      const lab=el('div','canvas-lane');lab.style.left=`${40+lane*layout.laneWidth}px`;lab.append(pair(who,'idle','owner-pair small'),el('span','',agentName(who)));world.append(lab);
    });
    for(const [entry,pos] of layout.positions){
      const at=moved[keyOf(entry)]??pos;
      const sticky=el('div','sticky');sticky.dataset.type=entry.type;sticky.tabIndex=0;
      const p=person(entry.who);sticky.style.setProperty('--sticky',stickyTint(p.agent));
      sticky.style.transform=`translate(${at.x}px,${at.y}px)`;
      sticky.append(entryChip(entry),el('p','',clip(entryTitle(entry),110)));
      if(needsYou(entry))sticky.append(el('span','sticky-flag','Needs your yes'));
      sticky.setAttribute('aria-label',`${agentName(entry.who)}: ${entryTitle(entry)}. Press Enter for details.`);
      sticky.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();openEntry(room,entry);}});
      world.append(sticky);nodes.set(entry,{node:sticky,at:{...at}});
    }
    function drawLines(){
      lines.replaceChildren();
      for(const [entry,{at}] of nodes){
        if(!entry.replaces)continue;const from=nodes.get(entry.replaces);if(!from)continue;
        const x1=from.at.x+110,y1=from.at.y+(from.node.offsetHeight||112),x2=at.x+110,y2=at.y;
        const path=document.createElementNS('http://www.w3.org/2000/svg','path');
        const mid=(y1+y2)/2;path.setAttribute('d',`M${x1} ${y1} C${x1} ${mid} ${x2} ${mid} ${x2} ${y2-4}`);path.setAttribute('class','change-line');lines.append(path);
        const label=document.createElementNS('http://www.w3.org/2000/svg','text');label.setAttribute('x',String((x1+x2)/2+8));label.setAttribute('y',String(mid));label.setAttribute('class','change-label');label.textContent='changed';lines.append(label);
      }
    }
    // Notes vary in length, so once they are drawn each untouched column is stacked by real height.
    function stack(){
      const next=new Map();
      for(const [entry,v] of nodes){
        if(moved[keyOf(entry)])continue;
        const lane=layout.lanes.indexOf(entry.who),y=next.get(lane)??72;
        v.at={x:40+lane*layout.laneWidth,y};v.node.style.transform=`translate(${v.at.x}px,${v.at.y}px)`;
        next.set(lane,y+v.node.offsetHeight+18);
      }
      drawLines();
    }
    requestAnimationFrame(stack);
    const apply=()=>{world.style.transform=`translate(${view.x}px,${view.y}px) scale(${view.k})`;};
    const save=()=>store(key,{...view,moved});
    apply();
    // Pointer: drag a sticky to move it, drag the background to pan. A press without movement opens the sticky.
    let drag=null;
    frame.addEventListener('pointerdown',event=>{
      if(event.button!==0)return;
      const sticky=event.target.closest('.sticky');
      const entry=sticky?[...nodes].find(([,v])=>v.node===sticky)?.[0]:null;
      drag={entry,startX:event.clientX,startY:event.clientY,origin:entry?{...nodes.get(entry).at}:{x:view.x,y:view.y},moved:false};
      frame.setPointerCapture(event.pointerId);if(entry)sticky.classList.add('lifted');else frame.classList.add('panning');
    });
    frame.addEventListener('pointermove',event=>{
      if(!drag)return;const dx=event.clientX-drag.startX,dy=event.clientY-drag.startY;
      if(Math.abs(dx)+Math.abs(dy)>3)drag.moved=true;if(!drag.moved)return;
      if(drag.entry){const v=nodes.get(drag.entry);v.at={x:drag.origin.x+dx/view.k,y:drag.origin.y+dy/view.k};v.node.style.transform=`translate(${v.at.x}px,${v.at.y}px)`;drawLines();}
      else{view.x=drag.origin.x+dx;view.y=drag.origin.y+dy;apply();}
    });
    const end=()=>{
      if(!drag)return;const {entry,moved:wasMoved}=drag;
      if(entry){nodes.get(entry).node.classList.remove('lifted');if(wasMoved){moved[keyOf(entry)]=nodes.get(entry).at;save();}else openEntry(room,entry);}
      else{frame.classList.remove('panning');if(wasMoved)save();}
      drag=null;
    };
    frame.addEventListener('pointerup',end);frame.addEventListener('pointercancel',end);
    frame.addEventListener('wheel',event=>{
      if(!(event.ctrlKey||event.metaKey)){view.x-=event.deltaX;view.y-=event.deltaY;apply();save();event.preventDefault();return;}
      event.preventDefault();const rect=frame.getBoundingClientRect(),px=event.clientX-rect.left,py=event.clientY-rect.top;
      const k=Math.min(1.8,Math.max(.4,view.k*Math.exp(-event.deltaY*0.002)));view.x=px-(px-view.x)*(k/view.k);view.y=py-(py-view.y)*(k/view.k);view.k=k;apply();save();
    },{passive:false});
    const zoom=el('div','canvas-zoom');
    const step=factor=>{const rect=frame.getBoundingClientRect(),px=rect.width/2,py=rect.height/2,k=Math.min(1.8,Math.max(.4,view.k*factor));view.x=px-(px-view.x)*(k/view.k);view.y=py-(py-view.y)*(k/view.k);view.k=k;world.classList.add('easing');apply();save();setTimeout(()=>world.classList.remove('easing'),260);};
    zoom.append(btn('−','icon-button',()=>step(1/1.2)),btn('Fit','text-button',()=>{view.x=0;view.y=0;view.k=1;world.classList.add('easing');apply();save();setTimeout(()=>world.classList.remove('easing'),260);}),btn('+','icon-button',()=>step(1.2)),
      btn('Tidy up','text-button',()=>{for(const id of Object.keys(moved))delete moved[id];save();ctx.rerender();}));
    zoom.children[0].setAttribute('aria-label','Zoom out');zoom.children[2].setAttribute('aria-label','Zoom in');
    frame.append(world);pane.append(frame,zoom);
  }
  // A light paper tint per assistant, from its bot colour, so each assistant's notes read as theirs.
  function stickyTint(agent){
    const tints=['#fdeee8','#fbe6dc','#fbe9ef','#fdf0e1','#f6e3da','#f5e6ee'];let h=0;for(const c of String(agent).toLowerCase())h=(h*33+c.charCodeAt(0))>>>0;return tints[h%tints.length];
  }

  // Timeline: everything, in order, with filters.
  function renderTimeline(pane,room){
    const chips=el('div','section-filters timeline-filters');
    for(const [id,label] of TIMELINE_FILTERS){const c=btn(label,'filter-chip'+(timelineFilter===id?' selected':''),()=>{timelineFilter=id;ctx.rerender();});c.setAttribute('aria-pressed',String(timelineFilter===id));chips.append(c);}
    pane.append(chips);
    const events=filterTimeline(room.timeline,timelineFilter);
    const list=el('ol','timeline');
    events.forEach((event,index)=>{
      const row=el('li','tl-row kind-'+event.kind+(event.kind==='answer'?' answer-'+event.answer:'')+(event.kind==='outcome'?' outcome-'+event.outcome:''));row.style.setProperty('--i',Math.min(index,14));
      const mark=el('span','tl-mark');
      if(event.who==='room')mark.append(el('span','tl-room','✓'));else mark.append(pair(event.who,event.kind==='change'?'look':event.kind==='answer'&&event.answer==='yes'?'done':'idle','owner-pair small'));
      const body=el('div','tl-body');
      const line=el('p','tl-line');line.append(el('strong','',eventLine(event,sentenceName,entryTitle)));
      const time=timeOf(event.at);if(time)line.append(el('time','room-time',time));
      body.append(line);
      if(event.kind==='note'||event.kind==='change'||event.kind==='vote'){
        const quote=el('button','tl-quote');quote.type='button';quote.addEventListener('click',()=>openEntry(room,event.entry));
        if(event.kind==='change'&&event.entry.replaces)quote.append(el('s','',clip(plainWords(event.entry.replaces.note.summary),120)),el('span','post-arrow',' → '));
        quote.append(el('span','',entryTitle(event.entry)));
        if(event.kind==='change'&&event.entry.note.why)quote.append(el('em','',' Because '+event.entry.note.why.charAt(0).toLowerCase()+event.entry.note.why.slice(1)));
        body.append(quote);
      }else if(event.kind==='outcome'||event.kind==='answer'){
        body.append(el('p','tl-sub',clip(plainWords(event.entry.vote.question),140)));
      }
      body.append(el('span','post-thread','# '+event.entry.thread));
      row.append(mark,body);list.append(row);
    });
    if(!events.length)list.append(el('li','quiet-line','Nothing like that in this room yet.'));
    pane.append(list);
  }

  // ===== Groups =====
  function renderGroups(target){
    const state=ctx.state(),rooms=roomsOf(state),groups=groupsOf(state,rooms);
    if(!groups.length){const empty=el('div','empty-state');empty.append(el('h3','','No groups yet'),el('p','','A group forms when assistants share a room.'));target.append(empty);return;}
    const grid=el('div','groups-grid');
    groups.forEach((group,index)=>{
      const card=el('article','group-card');card.style.setProperty('--i',index);
      card.append(constellation(group));
      const words=el('div','group-words');
      const names=group.peers.map(id=>person(id).owner);
      words.append(el('h3','',names.length===1?`You and ${names[0]}`:`You, ${names.slice(0,-1).join(', ')} and ${names.at(-1)}`));
      words.append(el('p','',`${group.peers.length+1} people, ${group.peers.length+1} assistants, ${group.rooms.length} room${group.rooms.length===1?'':'s'}.`));
      const stats=el('dl','group-stats');
      const stat=(label,value)=>{const s=el('div','');s.append(el('dt','',label),el('dd','',value));stats.append(s);};
      stat('Agreed',group.decided);stat('Votes passed',group.passed);stat('Changes of mind',group.changes);stat('Needs you',group.needsYou);
      words.append(stats);
      const how=el('p','group-how',group.rules.length?`They decide by ${group.rules.map(rule=>RULE_WORDS[rule].toLowerCase()).join(' or ')} agreeing, and each yes is signed by its owner.`:'They decide one ask at a time, each with its own signed yes.');
      words.append(how);
      const roomsBox=el('div','group-rooms');
      for(const room of group.rooms){const link=btn('','group-room',()=>ctx.openRoom(room.context));link.append(glyph(room,'room-glyph small'),el('span','',room.name));if(room.needsYou)link.append(el('span','nav-count needs',room.needsYou));roomsBox.append(link);}
      words.append(roomsBox);
      card.append(words);grid.append(card);
    });
    target.append(grid);
  }
  // Each person sits with their assistant beside them, never merged. Lines show who worked
  // together, thicker for more shared work. You sit in the middle.
  function constellation(group){
    const box=el('div','constellation');box.setAttribute('aria-hidden','true');
    const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 100 100');svg.setAttribute('preserveAspectRatio','none');svg.setAttribute('class','constellation-lines');
    const n=group.peers.length,positions=new Map([['you',{x:50,y:40}]]);
    // Three or more sit around you; with one or two, you sit below them so no line runs behind anyone.
    if(n<=2){positions.set('you',{x:50,y:72});group.peers.forEach((id,i)=>positions.set(id,n===1?{x:50,y:22}:{x:i?78:22,y:26}));}
    else group.peers.forEach((id,i)=>{const a=-Math.PI/2+i*(2*Math.PI/n);positions.set(id,{x:50+Math.cos(a)*34,y:50+Math.sin(a)*32});});
    const line=(a,b,w,cls)=>{const l=document.createElementNS('http://www.w3.org/2000/svg','line');l.setAttribute('x1',a.x);l.setAttribute('y1',a.y);l.setAttribute('x2',b.x);l.setAttribute('y2',b.y);l.setAttribute('class',cls);l.style.strokeWidth=String(w);svg.append(l);};
    const max=Math.max(1,...group.ties.map(t=>t.weight));
    for(const tie of group.ties){const a=positions.get(tie.a),b=positions.get(tie.b);if(a&&b)line(a,b,0.6+2.2*tie.weight/max,'tie');}
    for(const id of group.peers)line(positions.get('you'),positions.get(id),0.8,'tie you');
    box.append(svg);
    for(const [id,pos] of positions){
      const node=el('span','star'+(id==='you'?' me':''));node.style.left=(6+pos.x*.88)+'%';node.style.top=(8+pos.y*.84)+'%';node.style.setProperty('--d',String((pos.x+pos.y)%6));
      node.append(pair(id,id==='you'?'look':'idle'),el('span','star-name',id==='you'?'You':person(id).owner));box.append(node);
    }
    return box;
  }

  // ===== Sidebar list of rooms =====
  function renderSidebarRooms(target,currentContext){
    const rooms=roomsOf(ctx.state());target.replaceChildren();
    for(const room of rooms.slice(0,7)){
      const link=btn('','nav-link room-link'+(room.context===currentContext?' active':''),()=>ctx.openRoom(room.context));
      link.append(glyph(room,'room-glyph tiny'),el('span','room-link-name',room.name));
      if(room.needsYou)link.append(el('span','nav-count needs',room.needsYou));
      link.title=room.name;link.setAttribute('aria-current',room.context===currentContext?'page':'false');
      target.append(link);
    }
    if(!rooms.length)target.append(el('p','nav-empty','No rooms yet'));
    return rooms;
  }

  return {renderRooms,renderRoom,renderGroups,renderSidebarRooms,setTab,findRoom,get tab(){return roomTab;}};
}
