# Exit Liquidity — Style Guide

**Vibe target:** 70% dark trading-terminal / meme casino · 20% retro handheld
nostalgia · 10% absurd internet-sticker energy. Loud, legible, mobile-native.

## Colors
| Token | Hex | Use |
|---|---|---|
| `--bg0` | `#070a0f` | deepest background |
| `--bg1` | `#0d131c` | panel / gradient top |
| `--neon` | `#14f195` | primary brand, CTAs, SOL energy |
| `--good` | `#2bd97a` | positive objects, "catch" |
| `--cyan` | `#7df9ff` | UI accents, alpha, stats |
| `--gold` | `#ffd33d` | rare / jackpot / high score |
| `--red` | `#ff4d5e` | danger, lives, "dodge", fail |
| `--ink` | `#e7f0ee` | primary text |

Rule of thumb: **green/gold = grab it, red = avoid it.** Never blur that signal.

## Typography
- UI: system sans (`Segoe UI`/system-ui) — heavy weights (800–900) for scores & titles.
- Labels/captions: monospace, wide letter-spacing (`.12–.2em`) for terminal feel.
- Big numbers are the hero. Score should always be the loudest thing on screen.

## Iconography / objects
- Flat-shaded, high-contrast, single-glow silhouettes. Readable at ~24px.
- Each object reads instantly by **color + shape**, not detail.
- Glow = `shadowBlur` in the object's own accent color; keep it tight.

## Motion & feel ("juice")
- Catch: spark burst + floating `+score` + short rising blip; combo raises pitch.
- Rare: gold ring pop + ascending chime + mascot "hype" face.
- Fail: screen shake + red full-screen flash + descending buzzer + mascot "fail" face.
- Speed milestone: "⚡ warning" toast + small shake.
- Player movement eases (lerp), never teleports. Mascot idle-bobs.
- CRT scanlines + vignette always on for retro cohesion.

## Mascot direction
Original **degen goblin-trader**: green goblin face, hoodie with neon trim, gold
chain, glowing eyes, a glowing "catch tray". Three states: `idle`, `hype` (wide
eyes/grin, gold tray), `fail` (X eyes, frown, red tint). Sharp silhouette so it
works as avatar/sticker. Legally distinct — not based on any existing character.

## Layout
- Portrait-first, capped at 560px wide and centered on desktop.
- Safe touch targets ≥ 44px; lane buttons are large and bottom-anchored for thumbs.
- HUD top: score + lives left, pause right. Combo/warn float center.

## Voice (captions & copy)
Crypto-Twitter native, self-aware, a little unhinged, never mean. Examples:
"We are so back." / "Rugged at the top. Classic." / "Diamond hands certified."
See `WIN_CAPTIONS` / `FAIL_CAPTIONS` in `src/data.js`.

## Don'ts
- No gradients-on-gradients soup; one glow per element.
- No corporate-SaaS polish; keep it a little trashy and internet-native.
- No copyrighted characters, Soviet-cartoon or Nintendo references, in art or names.
