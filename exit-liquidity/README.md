# Exit Liquidity 💎

A one-screen viral arcade game: **catch the pump, dodge the rug.**
Mobile-first, instant-play, zero dependencies, no backend. Original art & theme
(meme-trading / degen internet culture) — inspired by the classic 4-lane catch
loop, but copies no characters, names, or layouts.

![status](https://img.shields.io/badge/MVP-playable-14f195) ![stack](https://img.shields.io/badge/stack-vanilla%20JS-7df9ff)

## Run it
No build step. It's static files served over HTTP (ES modules need a server, not `file://`):

```bash
cd exit-liquidity
python3 -m http.server 8080
# open http://localhost:8080
```
or any static server (`npx serve`, `npx http-server`, VS Code Live Server…).

## Play
- **Move** between 4 lanes: tap a lane, swipe, on-screen ◀ ▶, or arrow keys / A–D.
- **Catch green & gold** (candles, SOL bags, rockets, alpha, giga orbs) → points + combo.
- **Dodge red** (red candles, rug bombs, liquidation skulls) → catching one costs a life.
- **Missing good** also costs a life. You get **3**. Speed ramps the longer you survive.
- **Game over → Share** renders a square score card (Web Share on mobile, PNG download elsewhere).

## How it's built
| Concern | Choice | Why |
|---|---|---|
| Render | Canvas 2D, **procedural art** | near-zero load, infinitely scalable, easy recolor |
| Audio | **synthesized** WebAudio | no audio files |
| UI/screens | DOM overlays | crisp text, accessible, easy to theme |
| State | `localStorage` | best score + settings; seam for a future leaderboard |
| Deps | **none** | instant load, trivially hostable |

See [`docs/game-plan.md`](docs/game-plan.md), [`docs/style-guide.md`](docs/style-guide.md),
and [`docs/asset-list.md`](docs/asset-list.md).

## Tuning
- **What spawns / how often / how fast:** `src/data.js` (`OBJECTS`, weights, `difficultyAt`).
- **Rules, lives, combos, fx:** `src/game.js`.
- **Look:** `src/render.js` (objects, mascot, fx, CRT) + `styles/main.css` (colors/tokens).
- **Captions:** `WIN_CAPTIONS` / `FAIL_CAPTIONS` in `src/data.js`.

## Adding real art later
The MVP needs no binary assets. To add a raster mascot/banners:
drop PNGs into `assets/` and either wire `#art-slot` (in `index.html`) for menus,
or swap `drawMascot` in `render.js` for an image draw. Keep to the palette in the
style guide (neon green / red / gold / white on near-black), readable at 48px.

## Next steps
- Real leaderboard (drop-in at the `storage.js` seam) + daily seed.
- Branded raster mascot + social pack (X/TG headers, countdown, official-links card).
- Landing page + launch content.

> Note: lives inside the larger `FPF-bot` repo as a self-contained folder; it does
> not touch the Python project at the repo root.
