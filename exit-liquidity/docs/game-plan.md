# Exit Liquidity — Game Plan

A one-screen viral arcade game. **Catch the pump, dodge the rug.** Inspired by the
classic 4-lane "catch the falling thing" handheld loop, but fully original in art,
characters, naming, and theme (meme trading / degen internet culture).

## Pitch
- Understand in **5 seconds**, addictive in **30**.
- Mobile portrait first, instant-play, tiny load, no backend.
- Built-in shareable moments (high score, "rugged at X", combo brags).

## Core loop
1. Objects fall down **4 lanes**.
2. Player moves the mascot between 4 catch positions (tap lane / swipe / ◀▶ / arrows).
3. **Catch good** (green candle, SOL bag, alpha note, rocket, giga orb, insider).
4. **Dodge bad** (red candle, rug bomb, liquidation skull).
5. Lose a life if you **catch bad** or **miss good**. 3 lives.
6. Speed ramps with survival time. Combos multiply score. Game over → share.

### Scoring rules (the whole game in 4 lines)
| Event | Result |
|---|---|
| Good caught | `+points × multiplier`, combo +1 |
| Rare caught | jackpot points (never punishes if missed) |
| Bad caught | −1 life, combo reset |
| Good missed | −1 life, combo reset |
| Bad dodged | small `+2` bonus |

Multiplier = `1 + floor(combo / 5)`, capped at `6×`.

## Speed progression (first 120s)
Difficulty is a smooth ease toward a cap (`difficultyAt()` in `src/data.js`):

| Time | Feel | fallSpeed (×play-height/s) | spawn every |
|---|---|---|---|
| 0s | warmup, one at a time | ~0.34 | ~1.15s |
| 20s | picking up | ~0.50 | ~0.90s |
| 45s | fast lane, diagonals appear | ~0.63 | ~0.70s |
| 90s | degen hours | ~0.76 | ~0.50s |
| 120s | terminal velocity | ~0.80 (cap) | ~0.43s (cap) |

Milestones fire a "⚡ speed warning" + screen shake (see `SPEED_MILESTONES`).

## Screens
1. **Splash** — logo + blinking "press start" (~1.8s, tap to skip).
2. **Menu** — Play, How to play, best score, sound toggle.
3. **Game** — one-screen play + HUD (score, 3 lives, combo, warnings, lane buttons).
4. **Pause** — resume / quit / sound (auto-pauses when tab hidden).
5. **Game over** — score, best, survived, max combo, **Share**, replay, menu.
6. **How to play** — modal rules.

## Tech
- Vanilla **HTML + CSS + ES-module JS**. No build step, no dependencies, no backend.
- Gameplay on **Canvas 2D**; HUD/overlays are DOM for crisp text + a11y.
- All art is **procedural** (drawn in code) → near-zero load, infinitely scalable.
- Audio is **synthesized WebAudio** → zero audio files.
- Best score + settings in `localStorage` (seam ready for a future leaderboard API).

## File map
```
exit-liquidity/
  index.html            shell: canvas, HUD, all screen overlays
  styles/main.css       dark terminal-arcade theme
  src/
    main.js             boot, screen routing, HUD wiring
    game.js             core loop, state, rules, collisions, fx
    data.js             object catalog, spawn weights, speed curve, captions
    render.js           procedural Canvas art (objects, mascot, fx, CRT)
    input.js            keyboard / swipe / tap-lane / on-screen buttons
    audio.js            synthesized SFX
    storage.js          best score + settings (localStorage)
    sharecard.js        renders square share PNG + Web Share / download
  assets/               favicon.svg + slot for future raster art
  docs/                 this plan, asset list, style guide
```

## Roadmap
**MVP (done)**
- 4-lane catch/dodge, lives, combos, speed ramp, 6 screens, juicy fx, sound,
  share card, local best score, mobile + desktop.

**Launch**
- Real leaderboard (drop-in at `storage.js` seam) + daily challenge seed.
- Replace procedural mascot/share art with branded raster art (see asset-list).
- Landing page copy, X/Telegram banners, pinned "official links" card, countdown pack.

**Post-launch**
- Daily seed + streaks, unlockable mascot skins / meme object gallery.
- Power-ups (magnet, shield, 2× minute), weekly events, on-chain score attestations (optional).
