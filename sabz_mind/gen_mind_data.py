"""Generate 60s of real DQN brain activity for the 'Inside the Mind of SABZ'
visualization. Runs the trained brain inside the simulator with a demand
shift (NS-heavy -> EW-heavy) so judges see HOLDs and SWITCHes. Records the
18-dim state, hidden activations a1/a2, Q-values, decision and traffic
stats once per sim-second. Output: mind_data.json
"""
import json
import os
import sys

import numpy as np

WORK = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(WORK) or WORK)
sys.path.insert(0, os.path.join(WORK, ".."))

from sabz_rl import load_net, get_state  # noqa: E402
from sabz_sim2 import IntersectionV2, APPROACHES  # noqa: E402

NET_PATH = os.path.join(WORK, "..", "sabz_dqn_best.npz")

# 18 input labels, honest per sabz_rl.py get_state()
INPUT_LABELS = [
    "QUEUE N", "QUEUE S", "QUEUE E", "QUEUE W",
    "APPR N", "APPR S", "APPR E", "APPR W",
    "PHASE NS", "GREEN ELAPSED",
    "NEAR SCHOOL", "NEAR MOSQUE", "NEAR OFFICE", "NEAR HOSPITAL",
    "IS FRIDAY", "HOUR OF DAY",
    "RED WAIT", "MAX QUEUE AGE",
]

# Input value ranges for honest normalization in the viz
# (all already /20, /10, /60, /300 or binary except hour/24)
INPUT_MAX = [1.0] * 18


def rates(a, t):
    """Demand shift at t=30: NS rush -> EW rush. Forces real decisions."""
    if t < 30.0:
        return 0.28 if a in ("N", "S") else 0.035
    return 0.035 if a in ("N", "S") else 0.28


def main():
    net = load_net(NET_PATH)
    print("brain loaded:", NET_PATH, flush=True)

    sim = IntersectionV2(seed=7, safety_on=True)
    frames = []
    stats = {"switches": 0, "holds": 0, "safety_holds": 0}

    def decide(state, prio):
        sv = np.array(
            [state["queue"][a] / 20.0 for a in ("N", "S", "E", "W")]
            + [state["approaching"][a] / 10.0 for a in ("N", "S", "E", "W")]
            + [1.0 if state["phase"] == "NS" else 0.0,
               state["green_elapsed"] / 60.0]
            + [0.0] * 6
            + [state["red_wait"], state["max_q_age"]],
            dtype=np.float64,
        )
        q, (_x, _z1, a1, _z2, a2) = net.forward(sv)
        action = int(np.argmax(q))
        frames.append({
            "s": [round(float(v), 4) for v in sv],
            "a1": [round(float(v), 4) for v in a1],
            "a2": [round(float(v), 4) for v in a2],
            "q": [round(float(q[0]), 4), round(float(q[1]), 4)],
            "decision": action,
            "queue": {a: state["queue"][a] for a in APPROACHES},
            "appr": {a: state["approaching"][a] for a in APPROACHES},
            "phase": state["phase"],
            "green_elapsed": round(state["green_elapsed"], 2),
            "served": sim.served,
            "avg_delay": round(sim.delay_sum / max(sim.served, 1), 2),
            "t": round(sim.t, 1),
        })
        stats["switches" if action == 1 else "holds"] += 1
        return "switch" if action == 1 else "stay"

    T = 60.0
    while sim.t < T:
        sim.step(rates, decide)

    print(f"recorded {len(frames)} frames, "
          f"switches={stats['switches']} holds={stats['holds']} "
          f"safety_holds={sim.safety_holds}", flush=True)

    # per-layer activation scale for the viz (99th percentile, robust)
    all_a1 = np.array([f["a1"] for f in frames])
    all_a2 = np.array([f["a2"] for f in frames])
    scale = {
        "a1": float(np.percentile(all_a1, 99)) or 1.0,
        "a2": float(np.percentile(all_a2, 99)) or 1.0,
        "q_pos": float(max(max(f["q"]) for f in frames)) or 1.0,
        "q_neg": float(min(min(f["q"]) for f in frames)) or -1.0,
    }

    out = {
        "meta": {
            "arch": [18, 64, 64, 2],
            "params": 5506,
            "brain": "sabz_dqn_best.npz",
            "fps": 30,
            "seconds": 60,
            "frames": len(frames),
            "input_labels": INPUT_LABELS,
        },
        "scale": scale,
        "frames": frames,
    }
    path = os.path.join(WORK, "mind_data.json")
    with open(path, "w") as f:
        json.dump(out, f)
    print("wrote", path, f"({os.path.getsize(path)/1024:.0f} KB)", flush=True)


if __name__ == "__main__":
    main()
