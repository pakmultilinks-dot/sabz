# SABZ Live Interactive Demo

A live, interactive demonstration of the SABZ AI traffic controller for judges.

**What it is:** real traffic camera footage plays. AI detects every vehicle
in real time (green boxes). The trained DQN brain (`sabz_dqn_best.npz`)
reads the vehicle counts and decides, every second, whether to hold green
or switch the signal phase. Judges watch the brain think and can control
playback.

**Not a video. Not a simulation.** Detection runs live on the footage;
every brain decision comes from the real trained network.

## Run it

```bash
cd sabz_live_demo
./run.sh          # or: python3 server.py
```

Open http://localhost:8099 in Chrome. Works offline.

Needs: Python 3, `pip install flask numpy opencv-python-headless`.

## What judges see

- **Hero:** real camera feed with live AI detection boxes + vehicle count
- **Brain panel:** the DQN's live Q-values (HOLD vs SWITCH) as animated
  bars, the current decision, signal phase, green elapsed, switch count,
  per-approach vehicle queues (N/S/E/W)
- **Controls:** Play/Pause, Restart, speed 1x/2x/4x

## API

- `GET /api/state` - frame, counts, boxes, Q-values, decision, phase
- `GET /api/frame` - current annotated frame as base64 JPEG
- `POST /api/control` - {playing, speed, restart}
