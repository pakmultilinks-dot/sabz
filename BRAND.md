# SABZ Brand Guide

SABZ (سبز, "green" in Urdu) is AI-adaptive traffic signals for Pakistan.
The brand reads as a real infrastructure startup: dark, precise, glowing green.

## Logo

| File | Use |
|---|---|
| `logo.svg` / `logo.png` | Primary lockup (mark + wordmark). Default on dark backgrounds. |
| `logo-dark.svg` / `logo-dark.png` | Mark only. App icons, favicons, avatars, watermarks, dark surfaces. |
| `logo-light.svg` / `logo-light.png` | Full lockup with dark wordmark. Light backgrounds, print, documents. |

**The mark:** a traffic signal in a dark badge. Red and amber sit dim;
green burns bright with broadcast pulse rings, the AI signal going out.
The pole grounds it, it is street hardware, not a tech doodle.

**Clear space:** keep at least the height of the green lens empty on all sides.
**Minimum size:** 32 px for the mark, 120 px wide for the lockup.

### Do
- Use `logo.svg` on the dark dashboard and dark slides.
- Use `logo-light.svg` on white/light paper and light slides.
- Use `logo-dark.svg` alone as avatar, favicon, and social profile image.
- Let the green glow breathe, dark or neutral backgrounds behind it.

### Don't
- Don't recolor the green. Ever.
- Don't stretch, rotate, or add drop shadows.
- Don't place the dark lockup on busy photos without a dark scrim.
- Don't redraw the signal, the housing proportions are the logo.

## Color palette

| Name | Hex | Use |
|---|---|---|
| SABZ Green | `#00E676` | Primary. CTAs, wins, live indicators, logo glow |
| Deep Green | `#059669` | Tagline and accents on light backgrounds |
| Signal Red | `#F87171` | Danger, violations, stop states |
| Signal Amber | `#FBBF24` | Warnings, transitions |
| Ink | `#0B1220` | Page background (dark theme) |
| Card | `#141D33` | Cards and panels |
| Line | `#24304D` | Borders, dividers |
| Text | `#EDF2F7` | Headings and body on dark |
| Muted | `#93A1C0` | Secondary text, labels |

## Typography

### Primary pairing (use this)

1. **Headings, Space Grotesk, 700-800.** Geometric, technical, confident.
   https://fonts.google.com/specimen/Space+Grotesk
2. **Body, Inter, 400-600.** Clean, neutral, readable at any size.
   https://fonts.google.com/specimen/Inter
3. **Numbers and stats, JetBrains Mono, 500-700.** Tabular figures keep
   dashboard columns aligned; code-like feel suits telemetry.
   https://fonts.google.com/specimen/JetBrains+Mono

### Alternative pairing

Sora (headings) + Inter (body) + IBM Plex Mono (numbers).
https://fonts.google.com/specimen/Sora

### CSS

```css
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@500;700&display=swap');

:root {
  --green: #00E676;
  --deep-green: #059669;
  --red: #F87171;
  --amber: #FBBF24;
  --ink: #0B1220;
  --card: #141D33;
  --line: #24304D;
  --text: #EDF2F7;
  --muted: #93A1C0;
  --font-head: 'Space Grotesk', system-ui, sans-serif;
  --font-body: 'Inter', system-ui, sans-serif;
  --font-mono: 'JetBrains Mono', ui-monospace, monospace;
}

body { font-family: var(--font-body); background: var(--ink); color: var(--text); }
h1, h2, h3 { font-family: var(--font-head); font-weight: 700; letter-spacing: -0.01em; }
.stat, .number, td.num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.tagline { font-family: var(--font-head); font-weight: 600; letter-spacing: 0.32em; color: var(--green); }
```

### Type scale (suggestion)

- Display: Space Grotesk 800, 48-72 px, tight tracking
- H2: Space Grotesk 700, 28-36 px
- Body: Inter 400, 15-17 px, 1.6 line height
- Labels/tagline: Space Grotesk 600, uppercase, wide tracking (0.3em)
- Stats: JetBrains Mono 700, tabular numbers

## Voice

Short sentences. Numbers first. No hype words like "revolutionary".
Say what it does: "Green follows real demand." Say what it guarantees:
"Green is never cut inside the 70 m dilemma zone."
