"""SABZ judge demo backend: the REAL trained DQN brain drives a REAL traffic
simulator, live. Two intersections run in parallel on IDENTICAL traffic
(same seed): one controlled by the SABZ DQN brain, one by fixed-time timing.
"""
import os
import sys
import threading
import time
import numpy as np
from flask import Flask, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)
sys.path.insert(0, WORK)

from sabz_sim2 import (IntersectionV2, Vehicle, PHASES, OTHER, MIN_GREEN,
                       YELLOW, ALLRED, REAL_HEADWAYS, NGSIM_MEAN_GAP,
                       fixed_decide)
from sabz_rl import load_net, state_vec_from_dict

app = Flask(__name__, static_folder=".", static_url_path="")

# ---------------------------------------------------------------- brain ---
BRAIN_PATH = os.path.join(WORK, "sabz_dqn_best.npz")
net = load_net(BRAIN_PATH)
print("brain loaded:", BRAIN_PATH, flush=True)

# ------------------------------------------------------------- scenarios ---
SCENARIOS = {
    "normal":     {"label": "Normal Traffic",
                   "rates": lambda a, t: 0.12,
                   "seed": 101},
    "rush_hour":  {"label": "Rush Hour",
                   "rates": lambda a, t: 0.30,
                   "seed": 202},
    "asymmetric": {"label": "Asymmetric Flow",
                   "rates": lambda a, t: 0.25 if a in ("N", "S") else 0.035,
                   "seed": 303},
    "school_zone": {"label": "School Zone Surge",
                    "rates": lambda a, t: 0.30 if a in ("N", "S") else 0.08,
                    "seed": 404},
}

APPROACHES = ("N", "S", "E", "W")
ZERO_RATES = lambda a, t: 0.0  # internal spawner disabled; arrivals injected


class ArrivalGen:
    """Deterministic arrival schedule shared by both demo sims.

    Replicates the sim's real NGSIM headway sampler, but driven by our own
    RNG so the SABZ and fixed intersections face bit-identical traffic.
    (The sim's internal RNG diverges because observe() noise is skipped
    during yellow/all-red, which happens at different times per controller.)
    """

    def __init__(self, seed, rates_fn):
        self.rng = np.random.default_rng(seed)
        self.rates_fn = rates_fn
        self.next_t = {a: self._draw(a, 0.0) for a in APPROACHES}

    def _draw(self, a, t0):
        r = max(self.rates_fn(a, t0), 1e-6)
        if REAL_HEADWAYS:
            lane = str(self.rng.integers(1, 6))
            hw = REAL_HEADWAYS.get(lane, REAL_HEADWAYS.get('3'))
            if hw:
                u = self.rng.random()
                gap = hw['median'] * (hw['p90'] / hw['median']) ** (2 * u - 1)
                return t0 + max(0.5, gap / (r * NGSIM_MEAN_GAP))
        return t0 + self.rng.exponential(1.0 / r)

    def pop_due(self, a, t_now):
        out = []
        while self.next_t[a] <= t_now:
            t_arr = self.next_t[a]
            sp = max(8.0, float(self.rng.normal(12.0, 2.0)))
            dj = float(self.rng.uniform(0, 20))
            out.append((t_arr, sp, dj))
            self.next_t[a] = self._draw(a, t_arr)
        return out


class DemoSim:
    """One intersection instance with stable vehicle ids for the frontend."""

    def __init__(self):
        self.sim = None
        self.vid_by_obj = {}   # id(vehicle) -> vid
        self.next_vid = 1
        self.decide = None
        self.name = ""
        self.brain_info = None  # {"q_stay":..,"q_switch":..,"action":0/1,"executed":bool}
        self.prev_holds = 0

    def reset(self, name, rates, seed, decide):
        self.sim = IntersectionV2(seed=seed, safety_on=True)
        self.sim.use_real_data = False  # arrivals injected via ArrivalGen
        self.arrivals = ArrivalGen(seed, rates)
        self.vid_by_obj = {}
        self.next_vid = 1
        self.decide = decide
        self.name = name
        self.brain_info = None
        self.prev_holds = 0

    def _vid(self, v):
        k = id(v)
        vid = self.vid_by_obj.get(k)
        if vid is None:
            vid = self.next_vid
            self.next_vid += 1
            self.vid_by_obj[k] = vid
        return vid

    def prune(self):
        alive = set()
        for a in APPROACHES:
            for v in self.sim.veh[a]:
                alive.add(id(v))
        for k in [k for k in self.vid_by_obj if k not in alive]:
            del self.vid_by_obj[k]

    def lights(self):
        """Per-approach light color."""
        s = self.sim
        if s.transitioning:
            if s.trans_left > ALLRED:
                # yellow for the outgoing phase, red for the rest
                out = {}
                for a in APPROACHES:
                    out[a] = "yellow" if a in PHASES[s.phase] else "red"
                return out
            return {a: "red" for a in APPROACHES}
        out = {}
        for a in APPROACHES:
            out[a] = "green" if a in PHASES[s.phase] else "red"
        return out

    def snapshot(self):
        s = self.sim
        cars = {}
        for a in APPROACHES:
            lst = []
            for v in s.veh[a]:
                lst.append({"vid": self._vid(v),
                            "d": round(v.dist, 1),
                            "s": round(v.speed, 1),
                            "q": bool(v.queued)})
            cars[a] = lst
        self.prune()
        n = s.total or 1
        snap = {
            "t": round(s.t, 1),
            "phase": s.phase,
            "transitioning": bool(s.transitioning),
            "green_elapsed": round(s.green_elapsed, 1),
            "lights": self.lights(),
            "cars": cars,
            "queues": {a: len(s.queue_of(a)) for a in APPROACHES},
            "avg_delay": round(s.delay_sum / n, 2),
            "served": s.served,
            "total": s.total,
            "switches": s.switches,
            "safety_holds": s.safety_holds,
            "max_queue": s.max_queue,
        }
        if self.brain_info:
            snap["brain"] = self.brain_info
        return snap


# ------------------------------------------------------------- live state ---
STATE = {
    "scenario": "normal",
    "mode": "vs",          # vs | sabz | fixed  (frontend focus)
    "speed": 1,            # sim-seconds per tick
    "sabz": DemoSim(),
    "fixed": DemoSim(),
}

_last_brain = {}


def sabz_decide(state, prio):
    s = state_vec_from_dict(state)
    q, _ = net.forward(s)
    a = int(np.argmax(q))
    _last_brain["q_stay"] = float(q[0])
    _last_brain["q_switch"] = float(q[1])
    _last_brain["action"] = a
    return "switch" if a == 1 else "stay"


def fixed_decide_wrap(state, prio):
    return fixed_decide(state, prio)


def reset_all(scenario=None):
    if scenario:
        STATE["scenario"] = scenario
    sc = SCENARIOS[STATE["scenario"]]
    STATE["sabz"].reset("sabz", sc["rates"], sc["seed"], sabz_decide)
    STATE["fixed"].reset("fixed", sc["rates"], sc["seed"], fixed_decide_wrap)
    return sc["label"]


def step_once(dsim):
    """Advance one sim-second; record brain info for the SABZ side."""
    s = dsim.sim
    # Inject the shared deterministic arrivals due in this second, so both
    # intersections face identical traffic regardless of controller timing.
    t_target = s.t + 1.0
    for a in APPROACHES:
        for (t_arr, sp, dj) in dsim.arrivals.pop_due(a, t_target):
            s.veh[a].append(Vehicle(a, 200.0 + dj, sp, t_arr))
            s.total += 1
            s.last_arrival[a] = t_arr
    was_trans = s.transitioning
    holds_before = s.safety_holds
    s.step(ZERO_RATES, dsim.decide)
    if dsim.name == "sabz" and _last_brain:
        executed = (not was_trans) and s.transitioning
        safety_hold = s.safety_holds > holds_before
        dsim.brain_info = {
            "q_stay": round(_last_brain["q_stay"], 3),
            "q_switch": round(_last_brain["q_switch"], 3),
            "action": _last_brain["action"],
            "action_name": "switch" if _last_brain["action"] == 1 else "hold",
            "executed": executed,
            "safety_hold": safety_hold,
            "min_green_lock": s.green_elapsed < MIN_GREEN,
        }


reset_all("normal")

SIM_LOCK = threading.Lock()

# ---------------------------------------------------------------- routes ---
@app.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.route("/api/state")
def api_state():
    return jsonify({
        "scenario": STATE["scenario"],
        "scenario_label": SCENARIOS[STATE["scenario"]]["label"],
        "mode": STATE["mode"],
        "speed": STATE["speed"],
        "sabz": STATE["sabz"].snapshot(),
        "fixed": STATE["fixed"].snapshot(),
    })


@app.route("/api/step", methods=["POST"])
def api_step():
    body = request.get_json(silent=True) or {}
    n = int(body.get("n", STATE["speed"]))
    n = max(1, min(n, 20))
    with SIM_LOCK:
        for _ in range(n):
            step_once(STATE["sabz"])
            step_once(STATE["fixed"])
    return api_state()


@app.route("/api/mode", methods=["POST"])
def api_mode():
    body = request.get_json(silent=True) or {}
    m = body.get("mode", "vs")
    if m in ("vs", "sabz", "fixed"):
        STATE["mode"] = m
    return jsonify({"mode": STATE["mode"]})


@app.route("/api/speed", methods=["POST"])
def api_speed():
    body = request.get_json(silent=True) or {}
    sp = int(body.get("speed", 1))
    STATE["speed"] = sp if sp in (1, 2, 4, 8) else 1
    return jsonify({"speed": STATE["speed"]})


@app.route("/api/scenario", methods=["POST"])
def api_scenario():
    body = request.get_json(silent=True) or {}
    name = body.get("scenario", "normal")
    if name not in SCENARIOS:
        return jsonify({"error": "unknown scenario"}), 400
    with SIM_LOCK:
        label = reset_all(name)
    return jsonify({"scenario": name, "label": label})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    with SIM_LOCK:
        label = reset_all()
    return jsonify({"scenario": STATE["scenario"], "label": label})


@app.route("/api/stats")
def api_stats():
    out = {}
    for key in ("sabz", "fixed"):
        s = STATE[key].sim
        n = s.total or 1
        out[key] = {
            "avg_delay": round(s.delay_sum / n, 2),
            "served": s.served,
            "total": s.total,
            "throughput_h": round(s.served / max(s.t, 1) * 3600, 1),
            "switches": s.switches,
            "safety_holds": s.safety_holds,
            "max_queue": s.max_queue,
        }
    return jsonify(out)


@app.route("/api/scenarios")
def api_scenarios():
    return jsonify({k: v["label"] for k, v in SCENARIOS.items()})


if __name__ == "__main__":
    print("SABZ judge demo on http://localhost:8099", flush=True)
    app.run(host="0.0.0.0", port=8099, threaded=True)
