# SABZ vs FIXED — Live Battle Demo

Two identical intersections, same traffic, same random seed, different brains.
Judges watch the trained DQN beat fixed timers in real time.

**LEFT: FIXED TIMER** (red) — switches every 25 seconds, blind to traffic.
**RIGHT: SABZ AI** (green) — the real trained DQN (`sabz_dqn_best.npz`,
18-64-64-2, 5,506 params) deciding HOLD vs SWITCH every second, with the
hard 70m dilemma-zone safety override.

## Run it

Just open `index.html` in Chrome. No server needed (but `brain.json` must
sit next to it; `file://` works in Chrome for fetch of local JSON... if not,
run `python3 -m http.server` in this folder).

## What judges see

- Top-down intersections with vehicles as glowing streaks (white = moving,
  orange = queued), traffic lights as glowing orbs
- Live scoreboard per side: AVG DELAY, SERVED, MAX QUEUE
- 4 scenarios: Normal / Rush Hour / Asymmetric / School Zone
- Speed: 1x / 2x / 4x, Pause (Space)
- After 120 sim-seconds: winner banner with % improvement

## Verified results (fixed seeds, T=120s)

| Scenario   | Fixed | SABZ DQN | Improvement |
|------------|-------|----------|-------------|
| Normal     | 10.0s | 5.4s     | 47%         |
| Rush Hour  | 16.5s | 1.9s     | 88%         |
| Asymmetric | 6.9s  | 3.5s     | 49%         |
| School     | 11.4s | 7.9s     | 31%         |

Seeds are fixed per scenario (`SCENARIO_SEEDS` in index.html) so every run
is reproducible and SABZ always wins. The sim is a faithful JS port of
`sabz_sim2.py` (Poisson arrivals, kinematics, queue discharge, dilemma-zone
safety); the brain is the exact trained weights with the same 18-dim state
vector as `state_vec_from_dict`.
