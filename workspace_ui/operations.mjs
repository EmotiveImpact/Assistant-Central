// One workspace fence. Only the matching lease can release an operation.
// Clearing a panel's plaintext is not cancellation of its pending request.
export function operationGate(setBusy) {
  const pending=new Set();
  const publish=()=>setBusy(pending.size>0);
  function scope() {
    const owned=new Set();
    return {
      acquire() {
        const lease={};owned.add(lease);pending.add(lease);publish();
        return ()=>{if(owned.delete(lease)&&pending.delete(lease))publish();};
      },
      // Used only for a session end, never ordinary navigation/privacy cleanup.
      reset() { for(const lease of owned)pending.delete(lease);owned.clear();publish(); }
    };
  }
  const primary=scope();
  return {acquire:primary.acquire,scope,
    // The shell alone ends all old-session leases before a new account starts.
    reset(){pending.clear();publish();}};
}

// A different panel may have been hidden while the lease owner was pending.
// Defer restoration until its finally block has set uncertainty, and refuse a
// queued restoration if the account/session changed in the meantime.
export function restoreWhenIdle({session,eligible,restore}) {
  return ()=>{const stamp=session();queueMicrotask(()=>{if(stamp===session()&&eligible())restore();});};
}

// Retain each uncertainty source until its own authenticated inspection succeeds.
// A runtime catalogue read is not inspection of a conversation or draft store.
export function inspectionLatch() {
  const required=new Map();
  return {
    require(source,operation=null){if(!operation&&required.has(source))return required.get(source);const ticket={source,operation};required.set(source,ticket);return ticket;},
    capture:source=>required.get(source),
    clear(source,ticket){if(ticket&&required.get(source)===ticket)required.delete(source);},
    pending:()=>required.size>0,
    reset(){required.clear();}
  };
}
export async function inspectSavedState({latch,session,readState,inspectHost,inspectConversation=async()=>false}) {
  const stamp=session(),runtime=latch.capture('runtime'),host=latch.capture('host-drafts'),conversation=latch.capture('conversations');
  const state=await readState();
  if(stamp!==session())return null;
  latch.clear('runtime',runtime);
  if(host){
    const inspected=await inspectHost();
    if(stamp!==session())return null;
    if(inspected)latch.clear('host-drafts',host);
  }
  if(conversation){
    const inspected=await inspectConversation(conversation.operation);
    if(stamp!==session())return null;
    if(inspected===true)latch.clear('conversations',conversation);
  }
  // Unsupported conversation mutations remain held, never inferred from lists.
  return state;
}

// Only these explicitly opted-in local POSTs inspect state without authorising
// a conversation mutation. A write stays a write even if mislabelled by a caller.
export function requestIsMutation(path,method,readOnly=false) {
  const inspection=path==='/api/conversations/grants/list'||/^\/api\/conversations\/[A-Za-z0-9][A-Za-z0-9_-]{0,63}\/(?:history|read|context|grant-review|message-outcome)$/.test(path);
  return method!=='GET'&&!(method==='POST'&&readOnly&&inspection);
}
