# SABZ: AI-Adaptive Traffic Signals for Pakistan

SABZ replaces blind fixed-time traffic signals with camera-driven adaptive
green allocation, with a hard safety guarantee: green is never cut while a
vehicle is approaching the stop line. Built for the 4th International AI
Championship (AIEF), category **AI in Urban Tech**.

## The idea

Fixed timers waste green on empty roads while long queues wait on red. SABZ
counts vehicles per approach with cameras and gives green where the cars
actually are: extend green for long queues, cut it the instant a road clears,
skip empty approaches, never starve any road, and run time-of-day plans
learned from the map itself (schools, offices, mosques via OpenStreetMap).

Safety first: a 70 m dilemma zone is checked every second; any vehicle inside
it holds the green. Tested: 51 unsafe cutoffs without protection, 0 with it.

## What's here

- `sabz_sim.py` - v1 discrete-event simulator (fixed vs actuated).
- `sabz_sim2.py` - v2 kinematic simulator: vehicle agents with distance/speed,
  dilemma-zone safety as a hard rule, free-flow passes, queue dynamics.
- `sabz_rl.py` - our own DQN signal controller, trained from scratch in the
  simulator (safety stays a hard rule; the net learns efficiency only).
- `sabz_poi.py` - location intelligence: OpenStreetMap POIs around an
  intersection auto-generate time-of-day priority plans.
- `sabz_demo.py` - v1 scenarios, charts, animated side-by-side demo video.
- `test_safety.py` - safety proof: the accident scenario is real, the fix works.
- `eval_v2.py` - v2 full evaluation across scenarios.
- `proposal.md` - championship submission proposal.
- `keywords.txt` - the 5 submission keywords.

## Results (v2 kinematic sim, delay vs free-flow, 3 one-hour runs)

| Scenario | Fixed delay | SABZ delay | Cut |
|---|---|---|---|
| Asymmetric (2 vs 50 cars) | 8.7 s | 5.0 s | 43% |
| School morning rush | 11.0 s | 8.8 s | 20% |
| Balanced rush hour | 179.7 s | 11.9 s | 93% |

## Run it

```bash
pip install numpy matplotlib requests
python test_safety.py     # safety proof
python eval_v2.py         # full comparison
python sabz_rl.py         # train our DQN (background, ~30 min CPU)
python sabz_rl.py eval    # evaluate trained net vs actuated baseline
python sabz_poi.py        # location intelligence demo (needs Overpass API)
```

Simulation results are from the model, not road measurements; the control
logic and the safety guarantee are what is validated here.
