# Exit Liquidity — Asset Manifest

**Status legend:** ✅ shipped procedurally (drawn in code) · 🎨 optional raster upgrade · ⬜ todo for launch

Everything gameplay-facing is currently drawn in code (`src/render.js`), so the MVP
ships with **zero binary art files**. The "raster upgrade" column is what you'd
generate (Midjourney/Krea/etc.) and drop into `assets/` later for extra polish.

## Brand
| Asset | File | Size | Status | Notes |
|---|---|---|---|---|
| App / favicon icon | `assets/favicon.svg` | 64² | ✅ | "EL" gradient mark, readable at 48px |
| Logo wordmark | (CSS `.logo-word`) | — | ✅ | EXIT / LIQUIDITY stacked, neon |
| Social avatar | `assets/avatar.png` | 512² | 🎨 | reuse mark on dark bg |
| X/Twitter header | `assets/x-header.png` | 1500×500 | ⬜ | mascot + tagline + CA slot |
| Telegram header | `assets/tg-header.png` | 1920×1080 | ⬜ | same system, TG crop |
| "Official links" card | `assets/official-links.png` | 1080² | ⬜ | anti-scam verification card |

## In-game (all ✅ procedural)
| Asset | Where | Notes |
|---|---|---|
| Mascot (idle / hype / fail) | `render.js drawMascot` | degen goblin-trader, hoodie, gold chain, catch tray |
| Falling objects ×9 | `render.js drawObject` | green/red candle, SOL bag, alpha note, rocket, giga orb, insider, rug bomb, skull |
| Background | `render.js drawBackground` | scrolling candlestick wallpaper, market-night gradient |
| Lanes + catch line | `game.js render` | dashed neon catch line |
| FX: spark / shard / ring / score-float | `render.js drawParticle` | catch sparkle, rug shards, jackpot ring, +score |
| Screen shake + hit flash | `game.js` | red flash on life loss |
| CRT scanlines + vignette | `render.js drawCRT` | retro-handheld atmosphere |
| HUD (score, lives, combo, warn) | `styles/main.css` | DOM, neon |

## Social
| Asset | File / where | Size | Status |
|---|---|---|---|
| Score share card | `src/sharecard.js` (runtime PNG) | 1080² | ✅ generated per-run, Web Share / download |
| "Rugged at X" fail card | same (verdict = REKT) | 1080² | ✅ |
| "New high score" card | same (verdict = NEW HIGH SCORE) | 1080² | ✅ |
| Launch countdown 3/2/1 | `assets/countdown-*.png` | 1080² | ⬜ |
| Contract announcement | `assets/ca-announce.png` | 1080² | ⬜ |

## Audio (all ✅ synthesized in `audio.js`, no files)
move tick · catch ping · rare chime · miss crack · life-lost buzzer · combo · speed warning · game-over stinger · high-score jingle · start blip.

## Raster art slots (for later)
- `assets/mascot.png` — transparent PNG, the hero mascot. Wire into `#art-slot`
  (index.html) for menus, or swap `drawMascot` for an image draw in-game.
- Keep accents to **neon green / red / gold / white on near-black**; readable at
  48px; sticker-friendly silhouette. See `style-guide.md`.

## Generation prompts (if/when you add raster art)
- **Mascot:** "Original mascot for a meme-trading arcade game — chaotic degen
  trader, sleep-deprived, greedy, sharp silhouette, streetwear, expressive face,
  high-contrast, readable small, sticker/avatar ready. Dark bg, neon green + gold.
  Not cute, not corporate, not based on any copyrighted character."
- **Share card bg / countdown:** "Dark meme-trading social card, neon green/red/
  gold on near-black, faint candlestick texture, loud crypto-Twitter energy, room
  for big score numbers." (Card text is already composited at runtime.)
