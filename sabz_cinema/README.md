# SABZ Cinema - "The Eye That Never Blinks"

A cinematic interactive demo for the AI Championship judges.

## What it is

A 3-act film-like experience. Not a dashboard.

- **Act 1 - The Problem:** Lahore traffic footage, desaturated. Text reveals the problem.
  A red timer counts down while nothing changes. Click to continue.
- **Act 2 - The Awakening:** The same footage, now with the AI watching.
  Elegant glowing outlines track every vehicle. The real trained DQN brain
  decides HOLD vs SWITCH live (pre-computed from the actual model).
- **Act 3 - The Proof:** Split screen, FIXED TIMER vs SABZ AI.
  Numbers count up. Finale: سبز, "BUILT IN LAHORE. FOR LAHORE."

## Honest tech notes

- Detection boxes and brain decisions are PRE-COMPUTED from the real AI
  (OpenCV motion detection + the trained `sabz_dqn_best.npz` DQN), saved in
  `data.json`. This makes it instant and reliable for judges. Nothing is faked:
  every box and every decision came from the real pipeline.
- Footage: real street traffic video (rickshaws, dense mixed traffic).
- No server needed. No Python needed at demo time.

## Run it

Just open `index.html` in Chrome. Click through the acts with the dots
at the bottom, or click anywhere during Act 1 to advance.

Best shown full-screen (F11).
