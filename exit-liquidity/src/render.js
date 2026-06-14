// render.js — all visuals are drawn procedurally with Canvas 2D.
// No image/asset files: infinitely scalable, near-zero load, easy to recolor.
// Raster art (a Midjourney mascot etc.) can later be layered as an <img> slot;
// see assets/README and index.html #art-slot.

export const PALETTE = {
  bg0: '#070a0f',
  bg1: '#0d131c',
  grid: 'rgba(43, 217, 122, 0.07)',
  laneEdge: 'rgba(125, 249, 255, 0.10)',
  good: '#2bd97a',
  neon: '#14f195',
  cyan: '#7df9ff',
  orange: '#ff8a3d',
  gold: '#ffd33d',
  red: '#ff4d5e',
  redDeep: '#ff2e2e',
  bone: '#c9d2e0',
  ink: '#e7f0ee',
};

// ---------------------------------------------------------------------------
// Background: dark market-night terminal with faint candlestick wallpaper.
export function drawBackground(ctx, w, h, t) {
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, PALETTE.bg1);
  g.addColorStop(1, PALETTE.bg0);
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);

  // faint scrolling candlestick chart wallpaper
  ctx.save();
  ctx.globalAlpha = 0.5;
  const cw = 26, base = h * 0.62;
  const scroll = (t * 18) % cw;
  for (let i = -1, x = -scroll; x < w + cw; i++, x += cw) {
    const seed = Math.sin((i + Math.floor(t * 18 / cw)) * 12.9898) * 43758.5453;
    const r = seed - Math.floor(seed);
    const up = r > 0.5;
    const bodyH = 8 + r * 46;
    const y = base - r * 120;
    ctx.strokeStyle = ctx.fillStyle = up ? 'rgba(43,217,122,0.10)' : 'rgba(255,77,94,0.10)';
    ctx.fillRect(x + 7, y, cw - 14, bodyH);
    ctx.beginPath();
    ctx.moveTo(x + cw / 2, y - 10);
    ctx.lineTo(x + cw / 2, y + bodyH + 10);
    ctx.stroke();
  }
  ctx.restore();
}

// Lane guides inside the play rect.
export function drawLanes(ctx, rect, lanes) {
  const { x, y, w, h } = rect;
  const lw = w / lanes;
  ctx.save();
  ctx.strokeStyle = PALETTE.laneEdge;
  ctx.lineWidth = 1;
  for (let i = 1; i < lanes; i++) {
    ctx.beginPath();
    ctx.moveTo(x + i * lw, y);
    ctx.lineTo(x + i * lw, y + h);
    ctx.stroke();
  }
  ctx.restore();
}

function glow(ctx, color, blur) {
  ctx.shadowColor = color;
  ctx.shadowBlur = blur;
}

// ---------------------------------------------------------------------------
// Falling objects. Each centered at (x,y), sized to radius r.
export function drawObject(ctx, id, x, y, r, t) {
  ctx.save();
  ctx.translate(x, y);
  switch (id) {
    case 'green_candle': candle(ctx, r, PALETTE.good, true); break;
    case 'red_candle':   candle(ctx, r, PALETTE.red, false); break;
    case 'sol_bag':      solBag(ctx, r); break;
    case 'alpha_note':   alphaNote(ctx, r); break;
    case 'rocket':       rocket(ctx, r, t); break;
    case 'giga_orb':     gigaOrb(ctx, r, t); break;
    case 'insider':      insider(ctx, r); break;
    case 'rug_bomb':     rugBomb(ctx, r, t); break;
    case 'liq_skull':    skull(ctx, r); break;
    default:             candle(ctx, r, PALETTE.good, true);
  }
  ctx.restore();
}

function candle(ctx, r, color, up) {
  glow(ctx, color, 12);
  ctx.fillStyle = color;
  const bw = r * 1.0, bh = r * 1.7;
  ctx.fillRect(-bw / 2, -bh / 2, bw, bh);
  ctx.strokeStyle = color; ctx.lineWidth = Math.max(2, r * 0.14);
  ctx.beginPath();
  ctx.moveTo(0, -bh / 2 - r * 0.6); ctx.lineTo(0, -bh / 2);
  ctx.moveTo(0, bh / 2); ctx.lineTo(0, bh / 2 + r * 0.6);
  ctx.stroke();
  // little arrow hint
  ctx.shadowBlur = 0;
  ctx.fillStyle = 'rgba(7,10,15,0.85)';
  ctx.beginPath();
  if (up) { ctx.moveTo(0, -r * 0.35); ctx.lineTo(-r * 0.32, r * 0.05); ctx.lineTo(r * 0.32, r * 0.05); }
  else { ctx.moveTo(0, r * 0.35); ctx.lineTo(-r * 0.32, -r * 0.05); ctx.lineTo(r * 0.32, -r * 0.05); }
  ctx.closePath(); ctx.fill();
}

function solBag(ctx, r) {
  glow(ctx, PALETTE.neon, 12);
  ctx.fillStyle = '#0e3a2a';
  ctx.strokeStyle = PALETTE.neon; ctx.lineWidth = Math.max(2, r * 0.13);
  ctx.beginPath();
  ctx.moveTo(-r * 0.7, -r * 0.5);
  ctx.quadraticCurveTo(0, -r * 0.95, r * 0.7, -r * 0.5);
  ctx.lineTo(r * 0.85, r * 0.8);
  ctx.quadraticCurveTo(0, r * 1.05, -r * 0.85, r * 0.8);
  ctx.closePath(); ctx.fill(); ctx.stroke();
  // SOL "≡" mark
  ctx.shadowBlur = 0;
  ctx.strokeStyle = PALETTE.cyan; ctx.lineWidth = Math.max(2, r * 0.13);
  for (let i = -1; i <= 1; i++) {
    ctx.beginPath();
    ctx.moveTo(-r * 0.34, i * r * 0.26 + r * 0.08);
    ctx.lineTo(r * 0.34, i * r * 0.26 - r * 0.02);
    ctx.stroke();
  }
}

function alphaNote(ctx, r) {
  glow(ctx, PALETTE.cyan, 10);
  ctx.fillStyle = '#08222b';
  ctx.strokeStyle = PALETTE.cyan; ctx.lineWidth = Math.max(2, r * 0.12);
  roundRect(ctx, -r * 0.8, -r * 0.95, r * 1.6, r * 1.9, r * 0.18);
  ctx.fill(); ctx.stroke();
  ctx.shadowBlur = 0;
  ctx.fillStyle = PALETTE.cyan;
  ctx.font = `bold ${r * 0.95}px monospace`;
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText('α', 0, r * 0.04);
}

function rocket(ctx, r, t) {
  glow(ctx, PALETTE.orange, 14);
  // flame
  const f = 0.6 + Math.abs(Math.sin(t * 18)) * 0.5;
  ctx.fillStyle = PALETTE.gold;
  ctx.beginPath();
  ctx.moveTo(-r * 0.22, r * 0.55); ctx.lineTo(0, r * (0.55 + f)); ctx.lineTo(r * 0.22, r * 0.55);
  ctx.closePath(); ctx.fill();
  // body
  ctx.fillStyle = PALETTE.bone;
  ctx.beginPath();
  ctx.moveTo(0, -r * 0.95);
  ctx.quadraticCurveTo(r * 0.55, -r * 0.2, r * 0.4, r * 0.55);
  ctx.lineTo(-r * 0.4, r * 0.55);
  ctx.quadraticCurveTo(-r * 0.55, -r * 0.2, 0, -r * 0.95);
  ctx.closePath(); ctx.fill();
  // window
  ctx.shadowBlur = 0;
  ctx.fillStyle = PALETTE.orange;
  ctx.beginPath(); ctx.arc(0, -r * 0.15, r * 0.22, 0, Math.PI * 2); ctx.fill();
  // fins
  ctx.fillStyle = PALETTE.orange;
  ctx.beginPath(); ctx.moveTo(-r * 0.4, r * 0.2); ctx.lineTo(-r * 0.72, r * 0.6); ctx.lineTo(-r * 0.4, r * 0.55); ctx.closePath(); ctx.fill();
  ctx.beginPath(); ctx.moveTo(r * 0.4, r * 0.2); ctx.lineTo(r * 0.72, r * 0.6); ctx.lineTo(r * 0.4, r * 0.55); ctx.closePath(); ctx.fill();
}

function gigaOrb(ctx, r, t) {
  const pulse = 1 + Math.sin(t * 8) * 0.08;
  glow(ctx, PALETTE.gold, 26);
  const grad = ctx.createRadialGradient(0, 0, r * 0.1, 0, 0, r * pulse);
  grad.addColorStop(0, '#fff7cc');
  grad.addColorStop(0.5, PALETTE.gold);
  grad.addColorStop(1, '#b87b00');
  ctx.fillStyle = grad;
  ctx.beginPath(); ctx.arc(0, 0, r * pulse, 0, Math.PI * 2); ctx.fill();
  // rotating sparkle rays
  ctx.shadowBlur = 0;
  ctx.strokeStyle = 'rgba(255,255,255,0.85)'; ctx.lineWidth = Math.max(1.5, r * 0.08);
  for (let i = 0; i < 6; i++) {
    const a = t * 2 + i * Math.PI / 3;
    ctx.beginPath();
    ctx.moveTo(Math.cos(a) * r * 0.5, Math.sin(a) * r * 0.5);
    ctx.lineTo(Math.cos(a) * r * 1.25, Math.sin(a) * r * 1.25);
    ctx.stroke();
  }
}

function insider(ctx, r) {
  glow(ctx, PALETTE.gold, 12);
  ctx.fillStyle = '#2a2410';
  ctx.strokeStyle = PALETTE.gold; ctx.lineWidth = Math.max(2, r * 0.12);
  roundRect(ctx, -r * 0.9, -r * 0.65, r * 1.8, r * 1.3, r * 0.1);
  ctx.fill(); ctx.stroke();
  // envelope flap
  ctx.shadowBlur = 0;
  ctx.beginPath();
  ctx.moveTo(-r * 0.9, -r * 0.65); ctx.lineTo(0, r * 0.15); ctx.lineTo(r * 0.9, -r * 0.65);
  ctx.stroke();
  // wax seal
  ctx.fillStyle = PALETTE.red;
  ctx.beginPath(); ctx.arc(0, r * 0.05, r * 0.2, 0, Math.PI * 2); ctx.fill();
}

function rugBomb(ctx, r, t) {
  glow(ctx, PALETTE.redDeep, 16);
  ctx.fillStyle = '#1a0608';
  ctx.strokeStyle = PALETTE.redDeep; ctx.lineWidth = Math.max(2, r * 0.14);
  ctx.beginPath(); ctx.arc(0, r * 0.15, r * 0.85, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  // fuse + spark
  ctx.shadowBlur = 0;
  ctx.strokeStyle = PALETTE.bone; ctx.lineWidth = Math.max(2, r * 0.1);
  ctx.beginPath(); ctx.moveTo(r * 0.3, -r * 0.6); ctx.quadraticCurveTo(r * 0.8, -r * 0.9, r * 0.6, -r * 0.95); ctx.stroke();
  const s = 0.6 + Math.abs(Math.sin(t * 22)) * 0.6;
  ctx.fillStyle = PALETTE.gold; glow(ctx, PALETTE.orange, 12);
  ctx.beginPath(); ctx.arc(r * 0.6, -r * 0.95, r * 0.16 * s, 0, Math.PI * 2); ctx.fill();
  // skull-ish "RUG" mark
  ctx.shadowBlur = 0;
  ctx.fillStyle = PALETTE.redDeep;
  ctx.font = `bold ${r * 0.5}px monospace`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText('RUG', 0, r * 0.2);
}

function skull(ctx, r) {
  glow(ctx, PALETTE.bone, 10);
  ctx.fillStyle = PALETTE.bone;
  ctx.beginPath(); ctx.arc(0, -r * 0.1, r * 0.78, Math.PI, 0); ctx.fill();
  ctx.fillRect(-r * 0.78, -r * 0.1, r * 1.56, r * 0.7);
  // jaw
  ctx.fillRect(-r * 0.5, r * 0.55, r * 1.0, r * 0.32);
  // eyes + nose
  ctx.shadowBlur = 0;
  ctx.fillStyle = PALETTE.bg0;
  ctx.beginPath(); ctx.arc(-r * 0.32, -r * 0.1, r * 0.22, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.arc(r * 0.32, -r * 0.1, r * 0.22, 0, Math.PI * 2); ctx.fill();
  ctx.beginPath(); ctx.moveTo(0, r * 0.05); ctx.lineTo(-r * 0.12, r * 0.32); ctx.lineTo(r * 0.12, r * 0.32); ctx.closePath(); ctx.fill();
}

// ---------------------------------------------------------------------------
// The mascot: a chaotic degen goblin-trader in a hoodie, holding a catch tray.
// Drawn at lane center (x), sitting on baseline (y = bottom of play rect).
export function drawMascot(ctx, x, baseY, scale, state, t) {
  ctx.save();
  ctx.translate(x, baseY);
  ctx.scale(scale, scale);

  const bob = Math.sin(t * 6) * 2;
  const hype = state === 'hype';
  const fail = state === 'fail';

  // catch tray (always under the hands)
  ctx.save();
  glow(ctx, PALETTE.neon, hype ? 22 : 10);
  ctx.fillStyle = hype ? PALETTE.gold : PALETTE.neon;
  roundRect(ctx, -46, -18, 92, 12, 6);
  ctx.fill();
  ctx.restore();

  // body / hoodie
  ctx.fillStyle = fail ? '#3a1418' : '#15212e';
  ctx.strokeStyle = fail ? PALETTE.red : PALETTE.neon;
  ctx.lineWidth = 3;
  roundRect(ctx, -34, -64 + bob, 68, 52, 14);
  ctx.fill(); ctx.stroke();

  // hood + head
  ctx.fillStyle = fail ? '#4a1a20' : '#1c2b3a';
  ctx.beginPath();
  ctx.arc(0, -78 + bob, 26, 0, Math.PI * 2);
  ctx.fill(); ctx.stroke();

  // face (goblin green)
  ctx.fillStyle = '#7bd47a';
  ctx.beginPath();
  ctx.ellipse(0, -76 + bob, 17, 19, 0, 0, Math.PI * 2);
  ctx.fill();

  // eyes
  ctx.shadowBlur = 0;
  if (fail) {
    ctx.strokeStyle = '#0a0f14'; ctx.lineWidth = 3;
    cross(ctx, -7, -80 + bob, 4); cross(ctx, 7, -80 + bob, 4);
  } else {
    glow(ctx, hype ? PALETTE.gold : PALETTE.cyan, 10);
    ctx.fillStyle = hype ? PALETTE.gold : '#eaffff';
    ctx.beginPath(); ctx.arc(-7, -80 + bob, hype ? 5 : 4, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(7, -80 + bob, hype ? 5 : 4, 0, Math.PI * 2); ctx.fill();
    ctx.shadowBlur = 0;
    ctx.fillStyle = '#0a0f14';
    ctx.beginPath(); ctx.arc(-6, -80 + bob, 2, 0, Math.PI * 2); ctx.fill();
    ctx.beginPath(); ctx.arc(8, -80 + bob, 2, 0, Math.PI * 2); ctx.fill();
  }

  // mouth
  ctx.strokeStyle = '#0a0f14'; ctx.lineWidth = 2.5; ctx.beginPath();
  if (hype) { ctx.arc(0, -69 + bob, 7, 0, Math.PI); }
  else if (fail) { ctx.arc(0, -64 + bob, 6, Math.PI, 0); }
  else { ctx.moveTo(-6, -68 + bob); ctx.lineTo(6, -68 + bob); }
  ctx.stroke();

  // gold chain (degen detail)
  ctx.strokeStyle = PALETTE.gold; ctx.lineWidth = 2.4; glow(ctx, PALETTE.gold, 6);
  ctx.beginPath(); ctx.arc(0, -50 + bob, 14, 0.2 * Math.PI, 0.8 * Math.PI); ctx.stroke();

  ctx.restore();
}

// ---------------------------------------------------------------------------
// FX particles drawn from the game's fx list.
export function drawParticle(ctx, p) {
  ctx.save();
  ctx.globalAlpha = Math.max(0, p.life / p.max);
  ctx.translate(p.x, p.y);
  if (p.kind === 'spark') {
    glow(ctx, p.color, 10);
    ctx.fillStyle = p.color;
    ctx.beginPath(); ctx.arc(0, 0, p.r, 0, Math.PI * 2); ctx.fill();
  } else if (p.kind === 'shard') {
    ctx.rotate(p.rot);
    ctx.fillStyle = p.color;
    ctx.fillRect(-p.r, -p.r * 0.4, p.r * 2, p.r * 0.8);
  } else if (p.kind === 'ring') {
    ctx.strokeStyle = p.color; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.arc(0, 0, p.r, 0, Math.PI * 2); ctx.stroke();
  } else if (p.kind === 'float') {
    glow(ctx, p.color, 8);
    ctx.fillStyle = p.color;
    ctx.font = `bold ${p.r}px "Segoe UI", system-ui, sans-serif`;
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(p.text, 0, 0);
  }
  ctx.restore();
}

// CRT scanline + vignette overlay for the retro-handheld feel.
export function drawCRT(ctx, w, h) {
  ctx.save();
  ctx.globalAlpha = 0.06;
  ctx.fillStyle = '#000';
  for (let y = 0; y < h; y += 3) ctx.fillRect(0, y, w, 1);
  ctx.restore();
  const v = ctx.createRadialGradient(w / 2, h / 2, h * 0.35, w / 2, h / 2, h * 0.75);
  v.addColorStop(0, 'rgba(0,0,0,0)');
  v.addColorStop(1, 'rgba(0,0,0,0.45)');
  ctx.fillStyle = v;
  ctx.fillRect(0, 0, w, h);
}

// ---- small helpers --------------------------------------------------------
function roundRect(ctx, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
function cross(ctx, x, y, s) {
  ctx.beginPath();
  ctx.moveTo(x - s, y - s); ctx.lineTo(x + s, y + s);
  ctx.moveTo(x + s, y - s); ctx.lineTo(x - s, y + s);
  ctx.stroke();
}
