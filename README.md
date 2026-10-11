# SABZ: AI-Adaptive Traffic Signals for Pakistan

SABZ (سبز, "green") replaces blind fixed-time traffic signals with camera-driven
adaptive green allocation. Built for the 4th International AI Championship
(AIEF), category **AI in Urban Tech**.

## The idea

Fixed timers waste green on empty roads while long queues wait on red. SABZ
counts vehicles per approach with cameras and gives green where the cars
actually are: extend green for long queues, cut it the instant a road clears,
skip empty approaches, never starve any road, and run time-of-day plans
(school rush, Friday prayer, events).

## What's here

- `sabz_sim.py` - discrete-event 4-way intersection simulator: fixed-time vs
  SABZ adaptive controller, with camera detection noise modeled honestly.
- `sabz_demo.py` - runs 3 scenarios x 5 seeds, prints results, builds charts
  and the animated side-by-side demo video.
- `proposal.md` - championship submission proposal.
- `keywords.txt` - the 5 submission keywords.
- `chart_delay.png`, `chart_queues.png` - result charts.
- `sabz_demo.mp4` - 20 s animated demo: same traffic, fixed vs SABZ.

## Results (1-hour sim, 5 runs, identical traffic)

| Scenario | Fixed delay | SABZ delay | Cut |
|---|---|---|---|
| Asymmetric (2 vs 50 cars) | 217 s | 6 s | 97% |
| School morning rush | 55 s | 15 s | 73% |
| Balanced rush hour | 102 s | 34 s | 67% |

## Run it

```bash
pip install numpy matplotlib
python sabz_demo.py
```

Requires ffmpeg for the video. Simulation results are from the model, not road
measurements; the control logic is what is validated here.
