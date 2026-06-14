// storage.js — local persistence for best score + settings.
// No backend in MVP; this is the seam where a leaderboard API plugs in later.

const KEY = 'exitliq.v1';

const DEFAULTS = {
  best: 0,
  sound: true,
  plays: 0,
};

function read() {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) || '{}') };
  } catch {
    return { ...DEFAULTS };
  }
}

function write(state) {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
  } catch {
    /* private mode / storage disabled — game still works, just won't persist */
  }
}

export const store = {
  get best() { return read().best; },
  get sound() { return read().sound; },
  get plays() { return read().plays; },

  setBest(score) {
    const s = read();
    if (score > s.best) { s.best = score; write(s); return true; }
    return false;
  },
  setSound(on) { const s = read(); s.sound = !!on; write(s); },
  bumpPlays() { const s = read(); s.plays += 1; write(s); return s.plays; },
};
