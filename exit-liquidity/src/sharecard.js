// sharecard.js — renders a social-share score card to an offscreen canvas,
// then shares via the Web Share API (mobile) or falls back to download.
// Crypto-Twitter / Telegram native: dark, loud, big numbers.

import { PALETTE, drawMascot } from './render.js';
import { captionForRun } from './data.js';

const W = 1080, H = 1080; // square works everywhere (X, TG, IG)

export function renderShareCard({ score, best, time, bestCombo, won }) {
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const ctx = c.getContext('2d');

  // background
  const g = ctx.createLinearGradient(0, 0, 0, H);
  g.addColorStop(0, '#0d131c'); g.addColorStop(1, '#05070a');
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);

  // faint grid
  ctx.strokeStyle = 'rgba(43,217,122,0.06)'; ctx.lineWidth = 2;
  for (let x = 0; x < W; x += 60) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
  for (let y = 0; y < H; y += 60) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }

  // header / wordmark
  ctx.textAlign = 'center';
  ctx.fillStyle = PALETTE.neon;
  ctx.shadowColor = PALETTE.neon; ctx.shadowBlur = 24;
  ctx.font = '900 64px "Segoe UI", system-ui, sans-serif';
  ctx.fillText('EXIT LIQUIDITY', W / 2, 130);
  ctx.shadowBlur = 0;
  ctx.fillStyle = 'rgba(231,240,238,0.55)';
  ctx.font = '600 30px monospace';
  ctx.fillText('catch the pump · dodge the rug', W / 2, 178);

  // verdict chip
  const verdict = won ? 'NEW HIGH SCORE' : 'RUGGED';
  ctx.fillStyle = won ? PALETTE.gold : PALETTE.red;
  ctx.shadowColor = ctx.fillStyle; ctx.shadowBlur = 18;
  ctx.font = '800 40px "Segoe UI", system-ui, sans-serif';
  ctx.fillText(verdict, W / 2, 268);
  ctx.shadowBlur = 0;

  // big score
  ctx.fillStyle = PALETTE.ink;
  ctx.font = '900 240px "Segoe UI", system-ui, sans-serif';
  ctx.shadowColor = won ? PALETTE.gold : PALETTE.neon; ctx.shadowBlur = 30;
  ctx.fillText(String(score), W / 2, 540);
  ctx.shadowBlur = 0;
  ctx.fillStyle = 'rgba(231,240,238,0.6)';
  ctx.font = '700 34px monospace';
  ctx.fillText('SCORE', W / 2, 600);

  // stat row
  const stats = [
    ['SURVIVED', `${time}s`],
    ['BEST', String(best)],
    ['MAX COMBO', `x${bestCombo}`],
  ];
  const cw = 300, gap = 30, totalW = cw * 3 + gap * 2, sx = (W - totalW) / 2, sy = 660;
  stats.forEach(([label, val], i) => {
    const x = sx + i * (cw + gap);
    ctx.fillStyle = 'rgba(125,249,255,0.08)';
    roundRect(ctx, x, sy, cw, 130, 18); ctx.fill();
    ctx.strokeStyle = 'rgba(125,249,255,0.25)'; ctx.lineWidth = 2;
    roundRect(ctx, x, sy, cw, 130, 18); ctx.stroke();
    ctx.fillStyle = PALETTE.cyan; ctx.font = '800 56px "Segoe UI", system-ui, sans-serif';
    ctx.fillText(val, x + cw / 2, sy + 70);
    ctx.fillStyle = 'rgba(231,240,238,0.5)'; ctx.font = '600 24px monospace';
    ctx.fillText(label, x + cw / 2, sy + 108);
  });

  // mascot
  drawMascot(ctx, W / 2, 930, 1.8, won ? 'hype' : 'fail', 0);

  // caption
  ctx.fillStyle = 'rgba(231,240,238,0.85)';
  ctx.font = 'italic 600 32px "Segoe UI", system-ui, sans-serif';
  wrapText(ctx, `"${captionForRun(score, best, won)}"`, W / 2, 1010, W - 160, 40);

  return c;
}

export async function shareRun(run) {
  const canvas = renderShareCard(run);
  const blob = await new Promise(res => canvas.toBlob(res, 'image/png'));
  const file = new File([blob], 'exit-liquidity-score.png', { type: 'image/png' });
  const text = `I scored ${run.score} on Exit Liquidity 💎 catch the pump, dodge the rug.`;

  // Native share with image where supported (most mobile)
  if (navigator.canShare && navigator.canShare({ files: [file] })) {
    try { await navigator.share({ files: [file], text, title: 'Exit Liquidity' }); return 'shared'; }
    catch { /* user cancelled — fall through */ }
  }
  // Fallback: download the PNG so the player can post it manually
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'exit-liquidity-score.png';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  return 'downloaded';
}

// helpers
function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
function wrapText(ctx, text, cx, y, maxW, lh) {
  const words = text.split(' ');
  let line = '', lines = [];
  for (const w of words) {
    const test = line ? line + ' ' + w : w;
    if (ctx.measureText(test).width > maxW && line) { lines.push(line); line = w; }
    else line = test;
  }
  if (line) lines.push(line);
  lines.forEach((ln, i) => ctx.fillText(ln, cx, y + i * lh));
}
