# SABZ Product Architecture

AI-adaptive traffic signals for Pakistan. The product is the system,
not the demo.

## Components

| Module | File | Status |
|---|---|---|
| Brain (DQN controller) | `sabz_rl.py` | TRAINING (120k episodes) |
| Safety hard rule (dilemma zone) | `sabz_sim2.py` | Built, proven (51 unsafe cutoffs blocked) |
| LLM explanation layer | `sabz_explain.py` | Built (EN/UR, template fallback offline) |
| Continual learning (day-by-day) | `sabz_learn.py` | Built, tested |
| Location intelligence (OSM POIs) | `sabz_poi.py` | Built |
| Kinematic simulator | `sabz_sim2.py` | Built, evaluated |
| Judges dashboard | `sabz_dashboard.html` | Built (demo skin) |

## How the brain improves day by day

1. The controller logs every decision as (state, action, reward).
2. Nightly, training resumes from the checkpoint on fresh + logged data.
3. A challenger brain replaces the champion ONLY if it wins on the
   three benchmark scenarios. Never worse overnight.
4. The safety rule is outside the network and can never be trained away.

## LLM layer

Explains each signal decision in English or Urdu for officers and the
public, and writes end-of-day traffic reports with suggestions. Key from
`OPENROUTER_API_KEY` env var, never hardcoded. Works offline with
clearly-marked template explanations.
