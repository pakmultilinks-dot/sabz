# SABZ: AI-Adaptive Traffic Signals for Pakistan

**Category:** AI in Urban Tech | **4th International AI Championship (AIEF)**

SABZ (سبز, "green") replaces blind fixed-time traffic signals with an AI controller that gives green where the cars actually are. Cameras count vehicles per approach; the signal extends green for long queues, cuts it the instant a road clears, skips empty approaches, and never starves any road.

**The hard rule:** green is NEVER cut while a vehicle is in the 70 m dilemma zone approaching the stop line. This is physics, not AI, and no training run can override it.

## System components

| Module | File | What it does |
|---|---|---|
| Brain (DQN) | `sabz_rl.py` | Our own Deep Q-Network signal controller, trained from scratch in the simulator |
| Safety layer | `sabz_sim2.py` | Dilemma-zone hard rule, checked every second, overrides any unsafe switch |
| Simulator | `sabz_sim2.py` | Kinematic 4-way intersection with vehicle agents, queue dynamics, camera noise |
| Location intelligence | `sabz_poi.py` | Reads OpenStreetMap, finds schools/offices/mosques, auto-generates time-of-day plans |
| LLM explainer | `sabz_explain.py` | Explains every signal decision in English or Urdu; daily traffic reports |
| Continual learning | `sabz_learn.py` | Logs decisions, retrains nightly, only promotes the brain if it improves |
| Judges dashboard | `sabz_dashboard.html` | Live side-by-side: fixed timer vs actuated vs our trained neural net |

## Results

Kinematic simulation, same traffic for all controllers, safety active:

| Scenario | Fixed-time | SABZ actuated | SABZ brain (DQN) |
|---|---|---|---|
| Asymmetric (2 vs 50 cars) | 8.7 s | 5.0 s | **4.9 s** |
| School morning rush | 11.0 s | 8.8 s | — |
| Balanced rush hour | 179.7 s | 11.9 s | 13.3 s |

Safety: 51 unsafe cutoffs attempted without protection; 0 executed with it.

## The brain

- Architecture: 10 inputs → 64 ReLU → 64 ReLU → 2 Q-values (stay/switch)
- Training: behavioral-cloning warm start (86% accuracy) + DQN refinement
- Target: 120,000+ episodes; keeps training until it beats the hand-tuned controller on every scenario
- Weights: `models/sabz_dqn_best.npz`

## Quick start

```bash
# Run the simulator comparison
python3 eval_v2.py

# Train the brain (resumes from checkpoint)
python3 sabz_rl.py

# Explain a decision (needs OPENROUTER_API_KEY for LLM, else template)
python3 sabz_explain.py

# Open the judges dashboard
open sabz_dashboard.html
```

## Project

- Proposal: `proposal.md`
- Model card: `MODEL_CARD.md`
- Product architecture: `PRODUCT.md`
- Demo: `sabz_demo.mp4`

Built by Team SABZ, Lahore Garrison University.
