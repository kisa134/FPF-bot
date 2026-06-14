// input.js — unified controls: keyboard (arrows/A-D), swipe, tap-a-lane,
// and on-screen left/right buttons. Mobile portrait is the primary target.

export function attachInput(canvas, { lanes, getPlayRect, onMoveTo, onMoveBy, onAnyInput }) {
  // --- keyboard ---
  function onKey(e) {
    if (e.repeat) return;
    if (e.key === 'ArrowLeft' || e.key === 'a' || e.key === 'A') { onMoveBy(-1); onAnyInput?.(); }
    else if (e.key === 'ArrowRight' || e.key === 'd' || e.key === 'D') { onMoveBy(1); onAnyInput?.(); }
  }
  window.addEventListener('keydown', onKey);

  // --- pointer: tap a lane to jump there, or swipe to step ---
  let startX = 0, startY = 0, startT = 0, moved = false;
  function laneFromX(clientX) {
    const rect = getPlayRect();
    const canvasBox = canvas.getBoundingClientRect();
    const x = (clientX - canvasBox.left) * (canvas.width / canvasBox.width);
    const rel = (x - rect.x) / rect.w;
    return Math.max(0, Math.min(lanes - 1, Math.floor(rel * lanes)));
  }
  function down(e) {
    const p = point(e);
    startX = p.x; startY = p.y; startT = performance.now(); moved = false;
    onAnyInput?.();
  }
  function move(e) {
    const p = point(e);
    if (Math.abs(p.x - startX) > 28 && Math.abs(p.x - startX) > Math.abs(p.y - startY)) {
      onMoveBy(p.x > startX ? 1 : -1);
      startX = p.x; moved = true;
    }
  }
  function up(e) {
    const dt = performance.now() - startT;
    if (!moved && dt < 280) onMoveTo(laneFromX(point(e, true).x));
  }
  function point(e, isUp = false) {
    const src = e.changedTouches ? e.changedTouches[0] : (e.touches && e.touches[0]) || e;
    return { x: src.clientX, y: src.clientY };
  }

  canvas.addEventListener('pointerdown', down);
  canvas.addEventListener('pointermove', move);
  canvas.addEventListener('pointerup', up);
  // prevent scroll/zoom stealing gestures over the canvas
  canvas.addEventListener('touchmove', e => e.preventDefault(), { passive: false });

  return function detach() {
    window.removeEventListener('keydown', onKey);
    canvas.removeEventListener('pointerdown', down);
    canvas.removeEventListener('pointermove', move);
    canvas.removeEventListener('pointerup', up);
  };
}
