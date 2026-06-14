// game.js — core loop & state for Exit Liquidity.
// Rules (dead simple): CATCH the green/gold, DODGE the red.
//   • good caught  -> +points * combo multiplier
//   • good missed  -> lose a life
//   • rare caught  -> jackpot points (never punishes if missed)
//   • bad caught   -> lose a life (you grabbed a rug)
//   • bad dodged   -> small bonus
// 3 lives, speed ramps with survival time.

import { difficultyAt, pickObjectId, OBJECT_BY_ID, SPEED_MILESTONES } from './data.js';
import {
  drawBackground, drawLanes, drawObject, drawMascot, drawParticle, drawCRT, PALETTE,
} from './render.js';
import { sfx } from './audio.js';

export const LANES = 4;
const START_LIVES = 3;

export class Game {
  constructor(canvas, hooks = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.hooks = hooks;             // { onScore, onLives, onCombo, onWarn, onOver }
    this.running = false;
    this.paused = false;
    this._raf = null;
    this._lastMilestone = -1;
    this.reset();
  }

  reset() {
    this.objects = [];
    this.fx = [];
    this.score = 0;
    this.lives = START_LIVES;
    this.combo = 0;
    this.bestCombo = 0;
    this.t = 0;                     // survival seconds
    this.spawnTimer = 0;
    this.player = { lane: 1, x: 0, targetX: 0 };
    this.shake = 0;
    this.mascotState = 'idle';
    this.mascotTimer = 0;
    this.flash = null;              // {color, life}
    this._lastMilestone = -1;
  }

  // --- layout (recomputed on resize) ---
  layout() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const cssW = this.canvas.clientWidth || window.innerWidth;
    const cssH = this.canvas.clientHeight || window.innerHeight;
    this.canvas.width = Math.round(cssW * dpr);
    this.canvas.height = Math.round(cssH * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.W = cssW; this.H = cssH;
    const padX = Math.min(cssW * 0.04, 24);
    const top = cssH * 0.10;        // room for HUD
    const bottom = cssH * 0.06;
    this.rect = { x: padX, y: top, w: cssW - padX * 2, h: cssH - top - bottom };
    this.laneW = this.rect.w / LANES;
    this.objR = Math.max(16, Math.min(this.laneW * 0.30, 30));
    this.catchY = this.rect.y + this.rect.h - this.objR * 1.4;
    this.mascotScale = Math.max(0.7, Math.min(this.laneW / 110, 1.25));
    this.player.x = this.player.targetX = this.laneCenter(this.player.lane);
  }

  laneCenter(i) { return this.rect.x + (i + 0.5) * this.laneW; }
  getPlayRect() { return this.rect; }

  // --- controls ---
  moveTo(lane) {
    lane = Math.max(0, Math.min(LANES - 1, lane));
    if (lane !== this.player.lane) { this.player.lane = lane; this.player.targetX = this.laneCenter(lane); sfx.move(); }
  }
  moveBy(d) { this.moveTo(this.player.lane + d); }

  // --- lifecycle ---
  start() {
    this.reset();
    this.layout();
    this.running = true; this.paused = false;
    sfx.start();
    this.hooks.onScore?.(0);
    this.hooks.onLives?.(this.lives);
    this.hooks.onCombo?.(0, 1);
    this._last = performance.now();
    this._loop(this._last);
  }
  pause() { if (this.running) { this.paused = true; } }
  resume() {
    if (this.running && this.paused) { this.paused = false; this._last = performance.now(); this._loop(this._last); }
  }
  stop() { this.running = false; cancelAnimationFrame(this._raf); }

  get multiplier() { return Math.min(1 + Math.floor(this.combo / 5), 6); }

  // --- spawning ---
  spawn() {
    const diff = difficultyAt(this.t);
    const id = pickObjectId();
    const def = OBJECT_BY_ID[id];
    // avoid spawning two in the same lane too close together
    let lane = (Math.random() * LANES) | 0;
    for (let tries = 0; tries < 3; tries++) {
      const clash = this.objects.some(o => o.lane === lane && o.y < this.rect.y + this.rect.h * 0.25);
      if (!clash) break;
      lane = (Math.random() * LANES) | 0;
    }
    const diagonal = Math.random() < diff.diagChance && def.kind !== 'rare';
    this.objects.push({
      id, kind: def.kind, points: def.points, color: def.color,
      lane, x: this.laneCenter(lane), y: this.rect.y - this.objR,
      vx: diagonal ? (Math.random() < 0.5 ? -1 : 1) * this.laneW * 0.5 : 0,
      diagonal,
    });
  }

  // --- per-frame update ---
  update(dt) {
    this.t += dt;
    const diff = difficultyAt(this.t);

    // speed-warning milestones
    for (let i = 0; i < SPEED_MILESTONES.length; i++) {
      if (this.t >= SPEED_MILESTONES[i].at && i > this._lastMilestone) {
        this._lastMilestone = i;
        if (i > 0) { sfx.warn(); this.hooks.onWarn?.(SPEED_MILESTONES[i].note); this.shake = Math.max(this.shake, 6); }
      }
    }

    // spawning
    this.spawnTimer -= dt;
    if (this.spawnTimer <= 0) { this.spawn(); this.spawnTimer = diff.spawnEvery; }

    // player x easing
    this.player.x += (this.player.targetX - this.player.x) * Math.min(1, dt * 16);

    // mascot transient states
    if (this.mascotTimer > 0) { this.mascotTimer -= dt; if (this.mascotTimer <= 0) this.mascotState = 'idle'; }

    // move objects + resolve at catch line
    const fall = diff.fallSpeed * this.rect.h; // px/sec
    const half = this.laneW * 0.5;
    for (let i = this.objects.length - 1; i >= 0; i--) {
      const o = this.objects[i];
      o.y += fall * dt;
      if (o.vx) {
        o.x += o.vx * dt;
        if (o.x < this.rect.x + this.objR) { o.x = this.rect.x + this.objR; o.vx *= -1; }
        if (o.x > this.rect.x + this.rect.w - this.objR) { o.x = this.rect.x + this.rect.w - this.objR; o.vx *= -1; }
      }
      if (o.y >= this.catchY) {
        const caught = Math.abs(o.x - this.player.x) < half;
        this.resolve(o, caught);
        this.objects.splice(i, 1);
      }
    }

    // fx
    for (let i = this.fx.length - 1; i >= 0; i--) {
      const p = this.fx[i];
      p.life -= dt;
      p.x += (p.vx || 0) * dt;
      p.y += (p.vy || 0) * dt;
      if (p.vy != null) p.vy += 600 * dt;       // gravity for shards
      if (p.kind === 'ring') p.r += 240 * dt;
      if (p.rot != null) p.rot += (p.spin || 0) * dt;
      if (p.life <= 0) this.fx.splice(i, 1);
    }

    if (this.shake > 0) this.shake = Math.max(0, this.shake - dt * 30);
    if (this.flash) { this.flash.life -= dt; if (this.flash.life <= 0) this.flash = null; }
  }

  resolve(o, caught) {
    if (o.kind === 'good') {
      if (caught) this.scoreCatch(o);
      else this.loseLife('miss', o);
    } else if (o.kind === 'rare') {
      if (caught) this.scoreCatch(o, true);
      // missed rare = no penalty
    } else if (o.kind === 'bad') {
      if (caught) this.loseLife('rug', o);
      else { this.score += 2; this.hooks.onScore?.(this.score); }  // clean dodge bonus
    }
  }

  scoreCatch(o, rare = false) {
    this.combo += 1;
    this.bestCombo = Math.max(this.bestCombo, this.combo);
    const gained = o.points * this.multiplier;
    this.score += gained;
    this.hooks.onScore?.(this.score);
    this.hooks.onCombo?.(this.combo, this.multiplier);
    if (rare) { sfx.rare(); this.mascotState = 'hype'; this.mascotTimer = 0.7; this.burst(o.x, this.catchY, PALETTE.gold, 'ring'); }
    else { (this.combo > 1 ? sfx.combo(this.combo) : sfx.catch()); }
    this.burst(o.x, this.catchY, o.color, 'spark');
    this.float(o.x, this.catchY - 18, `+${gained}`, rare ? PALETTE.gold : o.color);
  }

  loseLife(reason, o) {
    this.combo = 0;
    this.lives -= 1;
    this.hooks.onCombo?.(0, 1);
    this.hooks.onLives?.(this.lives);
    this.mascotState = 'fail'; this.mascotTimer = 0.6;
    this.shake = 10;
    this.flash = { color: reason === 'rug' ? 'rgba(255,46,46,0.32)' : 'rgba(255,77,94,0.22)', life: 0.25 };
    if (reason === 'rug') { sfx.rug(); this.burst(o.x, this.catchY, PALETTE.redDeep, 'shard'); }
    else { sfx.miss(); sfx.lifeLost(); this.burst(o.x, this.catchY, PALETTE.red, 'shard'); }
    if (this.lives <= 0) this.gameOver();
  }

  gameOver() {
    this.running = false;
    cancelAnimationFrame(this._raf);
    sfx.over();
    this.hooks.onOver?.({ score: this.score, time: Math.floor(this.t), bestCombo: this.bestCombo });
  }

  // --- fx spawners ---
  burst(x, y, color, kind) {
    const n = kind === 'shard' ? 10 : kind === 'ring' ? 1 : 8;
    for (let i = 0; i < n; i++) {
      const a = (i / n) * Math.PI * 2 + Math.random();
      const sp = 80 + Math.random() * 160;
      this.fx.push({
        kind, color, x, y,
        vx: kind === 'ring' ? 0 : Math.cos(a) * sp,
        vy: kind === 'ring' ? null : Math.sin(a) * sp - (kind === 'shard' ? 120 : 0),
        r: kind === 'ring' ? 8 : 3 + Math.random() * 4,
        rot: Math.random() * Math.PI,
        spin: (Math.random() - 0.5) * 14,
        life: kind === 'ring' ? 0.4 : 0.5 + Math.random() * 0.3,
        max: 0.7,
      });
    }
  }
  float(x, y, text, color) {
    this.fx.push({ kind: 'float', text, color, x, y, vy: -70, r: 20, life: 0.8, max: 0.8 });
  }

  // --- render ---
  render() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.W, this.H);
    drawBackground(ctx, this.W, this.H, this.t);

    ctx.save();
    if (this.shake > 0) ctx.translate((Math.random() - 0.5) * this.shake, (Math.random() - 0.5) * this.shake);

    drawLanes(ctx, this.rect, LANES);

    // catch line
    ctx.strokeStyle = 'rgba(20,241,149,0.25)';
    ctx.setLineDash([6, 8]); ctx.lineWidth = 2;
    ctx.beginPath(); ctx.moveTo(this.rect.x, this.catchY); ctx.lineTo(this.rect.x + this.rect.w, this.catchY); ctx.stroke();
    ctx.setLineDash([]);

    for (const o of this.objects) drawObject(ctx, o.id, o.x, o.y, this.objR, this.t);
    drawMascot(ctx, this.player.x, this.rect.y + this.rect.h, this.mascotScale, this.mascotState, this.t);
    for (const p of this.fx) drawParticle(ctx, p);

    ctx.restore();

    if (this.flash) { ctx.fillStyle = this.flash.color; ctx.fillRect(0, 0, this.W, this.H); }
    drawCRT(ctx, this.W, this.H);
  }

  _loop(now) {
    if (!this.running || this.paused) return;
    const dt = Math.min(0.05, (now - this._last) / 1000);
    this._last = now;
    this.update(dt);
    this.render();
    this._raf = requestAnimationFrame(t => this._loop(t));
  }
}
