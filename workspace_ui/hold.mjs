// Hold to agree: money and consent need a deliberate hold of about a second while a coral
// ring fills. Letting go early does nothing. Callers always offer a plain button too.
export const HOLD_MS = 1000;

export function holdButton(label, onDone, {duration = HOLD_MS} = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'hold-control';
  const control = document.createElement('button');
  control.type = 'button';
  control.className = 'hold-button';
  control.setAttribute('aria-describedby', '');
  const ring = document.createElement('span');
  ring.className = 'hold-ring';
  ring.setAttribute('aria-hidden', 'true');
  const words = document.createElement('span');
  words.className = 'hold-label';
  words.textContent = label;
  control.append(ring, words);
  const hint = document.createElement('span');
  hint.className = 'hold-hint';
  hint.textContent = 'Press and hold for a second. Let go early and nothing happens.';
  wrap.append(control, hint);
  let start = 0, frame = 0, done = false;
  const paint = progress => control.style.setProperty('--hold', String(progress));
  const stop = () => { if (done) return; cancelAnimationFrame(frame); start = 0; paint(0); control.classList.remove('holding'); };
  const tick = now => {
    if (!start) return;
    const progress = Math.min(1, (now - start) / duration);
    paint(progress);
    if (progress >= 1) { done = true; control.classList.remove('holding'); control.classList.add('held'); control.disabled = true; onDone(); return; }
    frame = requestAnimationFrame(tick);
  };
  const begin = () => { if (done || start) return; start = performance.now(); control.classList.add('holding'); frame = requestAnimationFrame(tick); };
  control.addEventListener('pointerdown', event => { event.preventDefault(); begin(); });
  for (const type of ['pointerup', 'pointerleave', 'pointercancel']) control.addEventListener(type, stop);
  control.addEventListener('keydown', event => { if ((event.key === ' ' || event.key === 'Enter') && !event.repeat) { event.preventDefault(); begin(); } });
  control.addEventListener('keyup', event => { if (event.key === ' ' || event.key === 'Enter') stop(); });
  control.addEventListener('click', event => event.preventDefault());
  control.removeAttribute('aria-describedby');
  return wrap;
}
