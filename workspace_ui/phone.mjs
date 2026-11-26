// Questions on your phone: what the pairing panel shows. Pure, so it can be tested without a browser.
const MODES=new Set(['notice','full']);
const REASONS=new Set(['not_set_up','no_bot_token']);
const BOT=/^[A-Za-z0-9_]{5,32}$/;

// The server's answer is checked before anything is drawn from it.
export function validatePhone(status){
  if(!status||typeof status!=='object'||typeof status.paired!=='boolean'||typeof status.available!=='boolean')throw new Error('Unexpected phone status');
  if(!status.available){if(!REASONS.has(status.reason))throw new Error('Unexpected phone status');return status;}
  if(!MODES.has(status.mode)||(status.bot!==null&&!BOT.test(status.bot))||![true,false,null].includes(status.reachable))throw new Error('Unexpected phone status');
  return status;
}

// Only a Telegram start link for this bot and this code is ever drawn or opened.
export function startLink(made){
  if(!made||typeof made.code!=='string'||!/^[0-9a-f]{16}$/.test(made.code))return '';
  if(typeof made.bot!=='string'||!BOT.test(made.bot))return '';
  const link=`https://t.me/${made.bot}?start=${made.code}`;
  return made.start_link===link?link:'';
}

// One or two plain sentences for the top of the panel.
export function phoneNote(status){
  if(!status.available)return status.reason==='no_bot_token'
    ?'Phone questions are switched on, but the bot token is missing, so Parlu cannot reach Telegram. Approvals still shows every question.'
    :'Phone questions are not set up on this copy of Parlu. Approvals still shows every question.';
  const mode=status.mode==='full'
    ?'Your phone gets each question with its answers as buttons. Telegram chats are not end-to-end encrypted.'
    :'Your phone only hears that a question is waiting, never what it says. You answer here.';
  const reach=status.reachable===false?' Parlu cannot reach Telegram right now and keeps trying.':'';
  return mode+reach;
}

export const ANSWER_LIMIT='An answer is information for your assistant. It never approves sending, sharing, running or paying for anything.';
