# SABZ Live Judge Demo

A live, interactive demonstration of the SABZ AI traffic signal controller.
Two intersections run side by side on **identical traffic** (same deterministic
arrival schedule): one controlled by the real trained DQN brain
(`sabz_dqn_best.npz`), one by fixed-time timing. Judges watch the AI make
real decisions in real time and see the delay numbers race.

## Run it

```bash
cd sabz_judge_demo
./run.sh
```

Then open http://localhost:8099 in a browser (Chrome/Edge recommended).

`run.sh` starts the Flask backend, which serves the frontend too. No build
step. Three.js and the Space Grotesk font are vendored locally under
`lib/` and `fonts/`, so the demo works offline.

## What judges see

- **VS mode** (default): Fixed Timing on the left, SABZ AI on the right,
  same cars, live average-delay counters racing, "SABZ SAVES x.x s/veh" delta.
- **Brain view**: the DQN's live Q-values for HOLD vs SWITCH as animated
  bars, the chosen action, and why it did or didn't execute
  (executed / min-green lock / **safety hold: car in dilemma zone**).
- **Live delay chart**: both controllers' average delay over time.
- **Scenarios**: Normal, Rush Hour, Asymmetric, School Zone. One click
  resets both intersections onto the new demand pattern.
- **Speed**: 1x / 2x / 4x sim speed. Pause / Reset.
- **Focus modes**: VS, SABZ-only, Fixed-only (top-right buttons).

## How it works

`server.py` (Flask):
- Loads the trained DQN with `sabz_rl.load_net("sabz_dqn_best.npz")`.
- Every sim-second, each intersection steps `sabz_sim2.IntersectionV2`.
  The SABZ side asks the brain: `net.act(state_vec_from_dict(state))`.
- `ArrivalGen` replays the simulator's real NGSIM headway sampler from its
  own seeded RNG, so both sides face bit-identical traffic. (The sim's
  internal RNG can't be shared: `observe()` noise is skipped during
  yellow/all-red, which happens at different times per controller.)
- Hard dilemma-zone safety stays on: a switch the brain requests while a
  car is inside 70 m is overridden and counted as a safety hold.

`index.html` (Three.js, no build):
- Night intersection, wet-asphalt look, bloom, glowing signals, cars with
  headlights/taillights synced from backend positions (interpolated).
- Cars that clear the stop line keep driving through and out (the sim
  removes them at the line; the frontend animates the exit).

## API

- `GET  /api/state`      full snapshot of both intersections
- `POST /api/step`       `{n}` sim-seconds forward (1..20), returns snapshot
- `POST /api/mode`       `{mode: vs|sabz|fixed}` frontend focus hint
- `POST /api/speed`      `{speed: 1|2|4|8}`
- `POST /api/scenario`   `{scenario: normal|rush_hour|asymmetric|school_zone}`
- `POST /api/reset`      restart current scenario
- `GET  /api/stats`      cumulative delay/throughput/switches/holds
- `GET  /api/scenarios`  available scenarios

## Honest benchmark (600 sim-seconds each, identical traffic)

- normal:      SABZ 7.5s vs fixed 10.6s (SABZ wins)
- rush_hour:   SABZ 43.5s vs fixed 41.5s (both gridlocked, fixed slightly ahead)
- asymmetric:  SABZ 5.2s vs fixed 9.0s (SABZ wins)
- school_zone: SABZ 9.6s vs fixed 10.2s (SABZ wins)
