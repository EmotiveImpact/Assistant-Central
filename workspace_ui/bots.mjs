// Parlu assistant faces. Each assistant gets its own friendly bot, chosen from its
// name so it looks the same everywhere. Assistants are warm (coral family) and
// people are teal circles; a bot is always shown next to its owner.
const SVG = 'http://www.w3.org/2000/svg';
export const BODIES = ['#ee7b5b', '#f5a04a', '#e8679b', '#f2b33d', '#c4522f', '#b5476a'];
const INK = '#1b1a17', LIGHT = '#fbfaf7';

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
  const pick = (list, shift) => list[(h >>> shift) % list.length];
  return {
    body: pick(BODIES, 0),
    antenna: pick(['ball', 'ears', 'none', 'twin', 'leaf'], 3),
    eyes: pick(['dots', 'tall', 'happy', 'wink', 'wide', 'sleepy'], 7),
    mouth: pick(['smile', 'grin', 'o', 'flat'], 11),
    cheeks: ((h >>> 14) & 1) === 1,
  };
}

function el(name, attributes, parent) {
  // Minimal test documents may lack SVG support; the face is decorative, so fall back quietly.
  const node = typeof document.createElementNS === 'function' ? document.createElementNS(SVG, name) : document.createElement(name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  parent?.append(node);
  return node;
}

// An inline SVG bot face. Decorative: callers always show the name beside it.
export function botFace(name) {
  const t = botTraits(name);
  const svg = el('svg', {viewBox: '0 0 40 40', class: 'bot-face', 'aria-hidden': 'true', focusable: 'false'});
  const stroke = {stroke: t.body, 'stroke-width': 2.4, 'stroke-linecap': 'round', fill: 'none'};
  if (t.antenna === 'ball') { el('path', {d: 'M20 9V4.5', ...stroke}, svg); el('circle', {cx: 20, cy: 4, r: 2.6, fill: '#14897a'}, svg); }
  if (t.antenna === 'twin') { el('path', {d: 'M14 9.5 12 5M26 9.5 28 5', ...stroke}, svg); el('circle', {cx: 11.8, cy: 4.6, r: 2, fill: t.body}, svg); el('circle', {cx: 28.2, cy: 4.6, r: 2, fill: t.body}, svg); }
  if (t.antenna === 'ears') { el('rect', {x: 1.5, y: 17, width: 4, height: 9, rx: 2, fill: t.body}, svg); el('rect', {x: 34.5, y: 17, width: 4, height: 9, rx: 2, fill: t.body}, svg); }
  if (t.antenna === 'leaf') el('path', {d: 'M20 9.5C20 6 22.5 3.5 26 3.5C26 7 23.5 9.5 20 9.5Z', fill: '#14897a'}, svg);
  el('rect', {x: 4.5, y: 8.5, width: 31, height: 28, rx: 11, fill: t.body}, svg);
  el('rect', {x: 9, y: 14, width: 22, height: 15.5, rx: 7.5, fill: INK}, svg);
  const eye = {fill: LIGHT};
  const line = {stroke: LIGHT, 'stroke-width': 2, 'stroke-linecap': 'round', fill: 'none'};
  if (t.eyes === 'dots') { el('circle', {cx: 15, cy: 20.5, r: 2.3, ...eye}, svg); el('circle', {cx: 25, cy: 20.5, r: 2.3, ...eye}, svg); }
  if (t.eyes === 'tall') { el('rect', {x: 13.6, y: 17.5, width: 2.8, height: 6, rx: 1.4, ...eye}, svg); el('rect', {x: 23.6, y: 17.5, width: 2.8, height: 6, rx: 1.4, ...eye}, svg); }
  if (t.eyes === 'happy') el('path', {d: 'M12.6 21.5Q15 18 17.4 21.5M22.6 21.5Q25 18 27.4 21.5', ...line}, svg);
  if (t.eyes === 'wink') { el('circle', {cx: 15, cy: 20.5, r: 2.3, ...eye}, svg); el('path', {d: 'M22.6 20.8H27.4', ...line}, svg); }
  if (t.eyes === 'wide') { for (const cx of [15, 25]) { el('circle', {cx, cy: 20.5, r: 3, ...eye}, svg); el('circle', {cx: cx + .8, cy: 20, r: 1.2, fill: INK}, svg); } }
  if (t.eyes === 'sleepy') el('path', {d: 'M12.8 20Q15 22.5 17.2 20M22.8 20Q25 22.5 27.2 20', ...line}, svg);
  if (t.mouth === 'smile') el('path', {d: 'M17.5 25.3Q20 27.3 22.5 25.3', ...line, 'stroke-width': 1.6}, svg);
  if (t.mouth === 'grin') el('path', {d: 'M17 25H23Q22.5 27.6 20 27.6Q17.5 27.6 17 25Z', fill: '#ee7b5b'}, svg);
  if (t.mouth === 'o') el('circle', {cx: 20, cy: 26, r: 1.4, fill: LIGHT}, svg);
  if (t.mouth === 'flat') el('path', {d: 'M18 26H22', ...line, 'stroke-width': 1.6}, svg);
  if (t.cheeks) { el('circle', {cx: 8.5, cy: 28.5, r: 2, fill: LIGHT, opacity: .55}, svg); el('circle', {cx: 31.5, cy: 28.5, r: 2, fill: LIGHT, opacity: .55}, svg); }
  return svg;
}

// A person (teal circle with their initial, drawn by CSS) overlapping their bot.
// The initial comes from a data attribute, so the pair adds no text to the page.
export function ownerPair(owner, agent, className = 'owner-pair') {
  const pair = document.createElement('span');
  pair.className = className;
  pair.setAttribute('aria-hidden', 'true');
  const person = document.createElement('span');
  person.className = 'person-dot';
  person.dataset.initial = String(owner ?? '?').trim().slice(0, 1).toUpperCase() || '?';
  const bot = document.createElement('span');
  bot.className = 'bot-avatar';
  bot.append(botFace(agent));
  pair.append(person, bot);
  return pair;
}
