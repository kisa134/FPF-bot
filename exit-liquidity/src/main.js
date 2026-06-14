// main.js — boot, screen routing, HUD wiring. Ties the game to the DOM shell.

import { Game, LANES } from './game.js';
import { attachInput } from './input.js';
import { store } from './storage.js';
import { unlockAudio, setAudioEnabled, sfx } from './audio.js';
import { shareRun } from './sharecard.js';

const $ = sel => document.querySelector(sel);
const screens = {
  splash: $('#screen-splash'),
  menu: $('#screen-menu'),
  howto: $('#screen-howto'),
  pause: $('#screen-pause'),
  over: $('#screen-over'),
};
function show(name) {
  Object.entries(screens).forEach(([k, el]) => el.classList.toggle('hidden', k !== name && name !== 'game'));
  document.body.dataset.screen = name;
}
function hideAll() { Object.values(screens).forEach(el => el.classList.add('hidden')); }

const canvas = $('#game');
const game = new Game(canvas, {
  onScore: s => { $('#hud-score').textContent = s; },
  onLives: n => renderLives(n),
  onCombo: (c, mult) => renderCombo(c, mult),
  onWarn: note => flashWarn(note),
  onOver: run => onGameOver(run),
});

// ---- HUD ----
function renderLives(n) {
  const box = $('#hud-lives');
  box.innerHTML = '';
  for (let i = 0; i < 3; i++) {
    const d = document.createElement('span');
    d.className = 'life' + (i < n ? '' : ' lost');
    d.textContent = '◆';
    box.appendChild(d);
  }
}
let comboHideTimer = null;
function renderCombo(c, mult) {
  const el = $('#hud-combo');
  if (c >= 2) {
    el.textContent = `COMBO x${c}  ·  ${mult}×`;
    el.classList.add('show');
    el.classList.remove('pop'); void el.offsetWidth; el.classList.add('pop');
    clearTimeout(comboHideTimer);
    comboHideTimer = setTimeout(() => el.classList.remove('show'), 1400);
  } else {
    el.classList.remove('show');
  }
}
let warnTimer = null;
function flashWarn(note) {
  const el = $('#hud-warn');
  el.textContent = '⚡ ' + note;
  el.classList.add('show');
  clearTimeout(warnTimer);
  warnTimer = setTimeout(() => el.classList.remove('show'), 1600);
}

// ---- screen flow ----
function toMenu() {
  hideAll(); show('menu');
  $('#menu-best').textContent = store.best;
}
function startGame() {
  unlockAudio();
  hideAll();
  document.body.dataset.screen = 'game';
  $('#hud').classList.remove('hidden');
  game.layout();
  game.start();
}
function onGameOver(run) {
  $('#hud').classList.add('hidden');
  const isHigh = store.setBest(run.score);
  store.bumpPlays();
  if (isHigh && run.score > 0) sfx.highscore();
  $('#over-title').textContent = isHigh && run.score > 0 ? 'NEW HIGH SCORE' : 'REKT';
  $('#over-title').className = isHigh && run.score > 0 ? 'over-title high' : 'over-title';
  $('#over-score').textContent = run.score;
  $('#over-best').textContent = store.best;
  $('#over-time').textContent = run.time + 's';
  $('#over-combo').textContent = 'x' + run.bestCombo;
  game._lastRun = { ...run, best: store.best, won: isHigh && run.score > 0 };
  show('over');
}

// ---- buttons ----
$('#btn-play').addEventListener('click', startGame);
$('#btn-howto').addEventListener('click', () => { hideAll(); show('howto'); });
$('#btn-howto-back').addEventListener('click', toMenu);
$('#btn-replay').addEventListener('click', startGame);
$('#btn-menu').addEventListener('click', toMenu);
$('#btn-share').addEventListener('click', async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true; const label = btn.textContent; btn.textContent = '…';
  try { const r = await shareRun(game._lastRun); btn.textContent = r === 'shared' ? 'Shared ✓' : 'Saved ✓'; }
  catch { btn.textContent = 'Share'; }
  setTimeout(() => { btn.textContent = label; btn.disabled = false; }, 1600);
});

// pause
$('#btn-pause').addEventListener('click', () => { game.pause(); show('pause'); $('#hud').classList.add('hidden'); });
$('#btn-resume').addEventListener('click', () => { hideAll(); $('#hud').classList.remove('hidden'); document.body.dataset.screen = 'game'; game.resume(); });
$('#btn-quit').addEventListener('click', () => { game.stop(); toMenu(); });

// sound toggles (menu + pause share the state)
function syncSound() {
  const on = store.sound;
  setAudioEnabled(on);
  document.querySelectorAll('.btn-sound').forEach(b => { b.textContent = on ? '🔊' : '🔇'; b.setAttribute('aria-pressed', String(on)); });
}
document.querySelectorAll('.btn-sound').forEach(b =>
  b.addEventListener('click', () => { store.setSound(!store.sound); syncSound(); unlockAudio(); }));

// splash -> menu
$('#screen-splash').addEventListener('click', toMenu);
setTimeout(toMenu, 1800);

// ---- input + resize ----
attachInput(canvas, {
  lanes: LANES,
  getPlayRect: () => game.getPlayRect(),
  onMoveTo: lane => game.moveTo(lane),
  onMoveBy: d => game.moveBy(d),
  onAnyInput: unlockAudio,
});
// on-screen lane buttons
$('#btn-left').addEventListener('click', () => game.moveBy(-1));
$('#btn-right').addEventListener('click', () => game.moveBy(1));

let resizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => { if (document.body.dataset.screen === 'game') game.layout(); }, 120);
});
// pause if the tab is hidden mid-run
document.addEventListener('visibilitychange', () => {
  if (document.hidden && document.body.dataset.screen === 'game' && game.running && !game.paused) {
    game.pause(); show('pause'); $('#hud').classList.add('hidden');
  }
});

syncSound();
renderLives(3);
show('splash');
