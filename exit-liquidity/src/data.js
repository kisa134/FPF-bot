// data.js — content tables for Exit Liquidity
// Everything tunable about WHAT spawns and HOW the game ramps lives here.

// ---- Object catalog -------------------------------------------------------
// kind: 'good'  -> catch for points, missing it costs a life
//       'bad'   -> DON'T catch; catching it costs a life
//       'rare'  -> jackpot, big points, never penalizes
// weight: relative spawn frequency
// points: score on a successful catch (good/rare)
export const OBJECTS = [
  // --- good ---
  { id: 'green_candle', kind: 'good', label: 'Green candle', weight: 26, points: 10, color: '#2bd97a' },
  { id: 'sol_bag',      kind: 'good', label: 'Bag of SOL',   weight: 16, points: 15, color: '#14f195' },
  { id: 'alpha_note',   kind: 'good', label: 'Alpha note',   weight: 12, points: 20, color: '#7df9ff' },
  { id: 'rocket',       kind: 'good', label: 'Rocket',       weight: 12, points: 25, color: '#ff8a3d' },
  // --- rare ---
  { id: 'giga_orb',     kind: 'rare', label: 'Giga pump orb', weight: 4, points: 100, color: '#ffd33d' },
  { id: 'insider',      kind: 'rare', label: 'Insider envelope', weight: 3, points: 75, color: '#ffe680' },
  // --- bad ---
  { id: 'red_candle',   kind: 'bad',  label: 'Red candle',   weight: 14, points: 0, color: '#ff4d5e' },
  { id: 'rug_bomb',     kind: 'bad',  label: 'Rug bomb',     weight: 9,  points: 0, color: '#ff2e2e' },
  { id: 'liq_skull',    kind: 'bad',  label: 'Liquidation skull', weight: 6, points: 0, color: '#c9d2e0' },
];

export const OBJECT_BY_ID = Object.fromEntries(OBJECTS.map(o => [o.id, o]));

// Weighted bag for spawn picks, rebuilt once.
const SPAWN_BAG = OBJECTS.flatMap(o => Array(o.weight).fill(o.id));
export function pickObjectId(rng = Math.random) {
  return SPAWN_BAG[(rng() * SPAWN_BAG.length) | 0];
}

// ---- Speed / difficulty curve --------------------------------------------
// Difficulty is driven by elapsed survival time. Returns the tuning for "now".
// fallSpeed  : px/sec the objects descend (scaled by canvas height elsewhere)
// spawnEvery : seconds between spawns
// At t=0 it's gentle; it tightens up and plateaus so it stays fair-but-frantic.
export function difficultyAt(seconds) {
  const t = Math.max(0, seconds);
  // smooth ramp that eases toward a cap
  const ramp = 1 - Math.exp(-t / 45); // 0 -> ~1 over ~2 min
  const fallSpeed = 0.34 + 0.46 * ramp;            // fraction of play-height per second
  const spawnEvery = 1.15 - 0.72 * ramp;           // 1.15s -> ~0.43s
  const diagChance = 0.04 + 0.18 * ramp;           // odd diagonal drifters later
  return { fallSpeed, spawnEvery, diagChance, ramp };
}

// A readable table of milestones (used in docs + the How-to "speed warning" UI)
export const SPEED_MILESTONES = [
  { at: 0,   note: 'Warmup — one drop at a time' },
  { at: 20,  note: 'Picking up — watch the red' },
  { at: 45,  note: 'Fast lane — diagonals appear' },
  { at: 90,  note: 'Degen hours — near max speed' },
  { at: 120, note: 'Terminal velocity — pure reflex' },
];

// ---- Captions for the share / game-over card ------------------------------
// Picked by score band so the brag fits the run.
export const WIN_CAPTIONS = [
  'Caught the CEO tweet. Generational wealth incoming.',
  'Diamond hands certified. Paper hands DNI.',
  'Front-ran the whole timeline.',
  'We are so back.',
  'Exit liquidity? Not me. Never me.',
  'Sniped every orb. Insider behavior.',
  'Up only. I don’t know her (the dip).',
  'Locked in. Touched zero grass.',
];

export const FAIL_CAPTIONS = [
  'Rugged at the top. Classic.',
  'Caught the rug with both hands. Respect.',
  'It’s over. Wife’s boyfriend is disappointed.',
  'Liquidated. Sirens still ringing.',
  'Held the red candle like it was a baby.',
  'Became the exit liquidity. As foretold.',
  'Down bad. Coping in the group chat.',
  'GG. Touch grass, then re-enter.',
];

export function captionForRun(score, best, won = false) {
  const pool = won ? WIN_CAPTIONS : FAIL_CAPTIONS;
  let i = (score * 2654435761) >>> 0;       // cheap deterministic-ish hash
  i = i % pool.length;
  return pool[i];
}
