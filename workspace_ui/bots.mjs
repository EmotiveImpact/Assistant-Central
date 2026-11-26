// Parlu assistant faces: small blobs with two eyes, in warm colours. People stay teal
// circles. Shape and colour come from a hash of the assistant's name, so a bot looks the
// same everywhere. Expressions carry state. Bots never merge or overlap each other.
const SVG = 'http://www.w3.org/2000/svg';
export const SHAPES = {
  pebble: 'M50 7C77 7 94 23 94 51S77 94 49 94 6 79 6 51 23 7 50 7Z',
  bean: 'M28 12C48 4 60 18 76 20 92 22 96 40 92 56 86 82 66 94 44 92 20 90 6 72 8 52 10 32 14 17 28 12Z',
  cloud: 'M27 36C27 22 39 12 52 14 62 6 80 10 84 26 96 30 98 50 90 58 96 72 86 90 70 88 62 96 42 96 34 88 16 92 4 76 10 62 2 52 10 36 27 36Z',
  hex: 'M50 9 85 29V71L50 91 15 71V29Z',
  drop: 'M50 6C68 26 90 44 90 64A40 32 0 0 1 10 64C10 44 32 26 50 6Z',
  squircle: 'M50 6C84 6 94 16 94 50S84 94 50 94 6 84 6 50 16 6 50 6Z',
};
export const COLOURS = {coral: '#ee7b5b', rust: '#c4522f', rose: '#d9668a', amber: '#e08a2e', clay: '#a8441f', berry: '#9c4a6b'};
export const BODIES = Object.values(COLOURS);
export const EXPRESSIONS = ['idle', 'busy', 'look', 'done', 'sleep'];
const EYE = '#ffffff';

export function hashName(name) {
  let hash = 2166136261;
  for (const character of String(name ?? '').toLowerCase()) hash = Math.imul(hash ^ character.codePointAt(0), 16777619) >>> 0;
  // Final mix so similar names still get different traits.
  hash ^= hash >>> 16; hash = Math.imul(hash, 0x45d9f3b) >>> 0; hash ^= hash >>> 16;
  return hash >>> 0;
}

// The traits for one name. Pure, so tests and every view agree.
export function botTraits(name) {
  const h = hashName(name);
  const shapes = Object.keys(SHAPES), colours = Object.keys(COLOURS);
  const shape = shapes[h % shapes.length];
  const colour = colours[(h >>> 8) % colours.length];
  return {shape, colour, body: COLOURS[colour]};
}

function el(name, attributes, parent) {
  // Minimal test documents may lack SVG support; the face is decorative, so fall back quietly.
  const node = typeof document.createElementNS === 'function' ? document.createElementNS(SVG, name) : document.createElement(name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  parent?.append(node);
  return node;
}

function eyes(expression, svg) {
  const g = el('g', {class: 'bot-eyes'}, svg);
  const pill = (x, y, w, hgt, rot) => el('rect', {x, y, width: w, height: hgt, rx: w / 2, fill: EYE, ...(rot ? {transform: `rotate(${rot} ${x + w / 2} ${y + hgt / 2})`} : {})}, g);
  if (expression === 'done') el('path', {d: 'M33 52q7-9 14 0M55 52q7-9 14 0', stroke: EYE, 'stroke-width': 5.5, fill: 'none', 'stroke-linecap': 'round'}, g);
  else if (expression === 'sleep') el('path', {d: 'M33 52h13M56 52h13', stroke: EYE, 'stroke-width': 5, 'stroke-linecap': 'round'}, g);
  else if (expression === 'busy') { pill(34, 34, 8, 14, 14); pill(52, 32, 8, 14, 14); }
  else if (expression === 'look') { pill(35, 38, 10, 17); pill(56, 38, 10, 17); }
  else { pill(36, 38, 8, 15, 10); pill(56, 38, 8, 15, 10); }
}

// An inline SVG bot face. Decorative: callers always show the name and state as text.
export function botFace(name, expression = 'idle') {
  const t = botTraits(name);
  const svg = el('svg', {viewBox: '0 0 100 100', class: 'bot-face', 'aria-hidden': 'true', focusable: 'false', 'data-shape': t.shape, 'data-expression': expression});
  if (expression === 'look') el('path', {d: SHAPES[t.shape], fill: 'none', stroke: COLOURS.coral, 'stroke-width': 5, opacity: .55, transform: 'translate(50 50) scale(1.16) translate(-50 -50)'}, svg);
  const round = t.shape === 'hex' ? {stroke: t.body, 'stroke-width': 12, 'stroke-linejoin': 'round'} : {};
  el('path', {d: SHAPES[t.shape], fill: t.body, ...round}, svg);
  eyes(expression, svg);
  return svg;
}

function initialOf(owner) { return String(owner ?? '?').trim().slice(0, 1).toUpperCase() || '?'; }

// The owner's teal circle with the assistant's bot beside it, 4px apart, never overlapping.
// The initial comes from a data attribute, so the pair adds no text to the page.
export function ownerPair(owner, agent, className = 'owner-pair', expression = 'idle') {
  const pair = document.createElement('span');
  pair.className = className;
  pair.setAttribute('aria-hidden', 'true');
  const person = document.createElement('span');
  person.className = 'person-dot';
  person.dataset.initial = initialOf(owner);
  const bot = document.createElement('span');
  bot.className = 'bot-avatar';
  bot.append(botFace(agent, expression));
  pair.append(person, bot);
  return pair;
}
