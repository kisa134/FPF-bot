// audio.js — all SFX synthesized with WebAudio. Zero audio files = instant load.
// Each cue is a tiny oscillator/noise burst shaped to feel "arcade".

let ctx = null;
let master = null;
let enabled = true;

function ensure() {
  if (ctx) return ctx;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return null;
  ctx = new AC();
  master = ctx.createGain();
  master.gain.value = 0.32;
  master.connect(ctx.destination);
  return ctx;
}

// Browsers require a user gesture to start audio — call this on first tap/key.
export function unlockAudio() {
  const c = ensure();
  if (c && c.state === 'suspended') c.resume();
}

export function setAudioEnabled(on) { enabled = !!on; }

function tone({ freq = 440, type = 'square', dur = 0.12, gain = 0.6, slideTo = null, delay = 0 }) {
  if (!enabled) return;
  const c = ensure();
  if (!c) return;
  const t0 = c.currentTime + delay;
  const osc = c.createOscillator();
  const g = c.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (slideTo) osc.frequency.exponentialRampToValueAtTime(slideTo, t0 + dur);
  g.gain.setValueAtTime(0.0001, t0);
  g.gain.exponentialRampToValueAtTime(gain, t0 + 0.008);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(g); g.connect(master);
  osc.start(t0); osc.stop(t0 + dur + 0.02);
}

function noise({ dur = 0.18, gain = 0.5, hp = 600 }) {
  if (!enabled) return;
  const c = ensure();
  if (!c) return;
  const t0 = c.currentTime;
  const frames = (c.sampleRate * dur) | 0;
  const buf = c.createBuffer(1, frames, c.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < frames; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / frames);
  const src = c.createBufferSource(); src.buffer = buf;
  const filt = c.createBiquadFilter(); filt.type = 'highpass'; filt.frequency.value = hp;
  const g = c.createGain();
  g.gain.setValueAtTime(gain, t0);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  src.connect(filt); filt.connect(g); g.connect(master);
  src.start(t0); src.stop(t0 + dur);
}

export const sfx = {
  move:    () => tone({ freq: 320, type: 'square', dur: 0.05, gain: 0.25 }),
  catch:   () => tone({ freq: 520, type: 'square', dur: 0.10, gain: 0.5, slideTo: 880 }),
  rare:    () => { tone({ freq: 660, dur: 0.1, gain: 0.5, slideTo: 990 }); tone({ freq: 990, dur: 0.12, gain: 0.45, slideTo: 1480, delay: 0.09 }); },
  combo:   (n) => tone({ freq: 440 + Math.min(n, 12) * 40, type: 'triangle', dur: 0.08, gain: 0.4 }),
  miss:    () => noise({ dur: 0.14, gain: 0.4, hp: 400 }),
  rug:     () => { tone({ freq: 200, type: 'sawtooth', dur: 0.28, gain: 0.55, slideTo: 60 }); noise({ dur: 0.3, gain: 0.4, hp: 200 }); },
  lifeLost:() => tone({ freq: 300, type: 'sawtooth', dur: 0.3, gain: 0.5, slideTo: 110 }),
  start:   () => { tone({ freq: 440, dur: 0.08, gain: 0.4 }); tone({ freq: 660, dur: 0.1, gain: 0.4, delay: 0.08 }); },
  warn:    () => tone({ freq: 880, type: 'triangle', dur: 0.07, gain: 0.3 }),
  over:    () => { tone({ freq: 440, type: 'sawtooth', dur: 0.18, gain: 0.5, slideTo: 330 }); tone({ freq: 330, type: 'sawtooth', dur: 0.2, gain: 0.5, slideTo: 220, delay: 0.18 }); tone({ freq: 220, type: 'sawtooth', dur: 0.35, gain: 0.5, slideTo: 110, delay: 0.36 }); },
  highscore:() => { [660, 880, 1100, 1320].forEach((f, i) => tone({ freq: f, dur: 0.12, gain: 0.45, delay: i * 0.1 })); },
};
