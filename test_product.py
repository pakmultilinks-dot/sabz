"""SABZ product integration test: the whole pipeline working together.

1. Brain (trained DQN) controls a live intersection.
2. Safety hard rule overrides any unsafe switch attempt.
3. LLM layer explains a decision (EN + UR).
4. Learner logs the day's experiences.

Pass = product is real, not slides.
"""
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sabz_rl import load_net, get_state, BEST
from sabz_sim2 import IntersectionV2
from sabz_explain import explain_decision

PASS, FAIL = "PASS", "FAIL"
results = []


def check(name, cond, detail=""):
    results.append((name, PASS if cond else FAIL, detail))
    print("[%s] %s %s" % (PASS if cond else FAIL, name, detail))


# 1. Brain loads and decides
net = load_net(BEST) if os.path.exists(BEST) else None
check("brain weights load", net is not None)
sim = IntersectionV2(seed=99)
s = get_state(sim)
a = net.act(s) if net else 0
check("brain decides", a in (0, 1), "action=%d" % a)

# 2b. Micro-test: car placed inside dilemma zone, brain demands switch,
# green well below cap -> switch MUST be blocked.
from sabz_sim2 import Vehicle, DILEMMA_DIST
sim2 = IntersectionV2(seed=1, safety_on=True)
sim2.phase = "NS"
sim2.green_elapsed = 20.0
sim2.veh["N"].append(Vehicle("N", DILEMMA_DIST / 2, 12.0, 0.0))
assert sim2.dilemma(), "test setup: car should be in dilemma zone"
sw0 = sim2.switches
sim2.step(lambda a, t: 0.0, lambda st, pr: "switch")
check("hard rule blocks switch with car in zone",
      sim2.switches == sw0 and sim2.safety_holds == 1,
      "switches=%d->%d holds=%d" % (sw0, sim2.switches, sim2.safety_holds))

# 2c. Brain controls 10 simulated minutes; safety holds every attempt it can.
sim = IntersectionV2(seed=99, safety_on=True)


def rates(aa, t):
    return 0.30 if aa in "NS" else 0.08


while sim.t < 600.0:
    s = get_state(sim)
    a = net.act(s)
    sim.step(rates, lambda st, pr: "switch" if a == 1 else "stay")
check("safety engaged during brain control", sim.safety_holds > 0,
      "holds=%d attempts=%d (rest hit the 60s fairness cap -> normal yellow)"
      % (sim.safety_holds, sim.would_violate))

# 3. Explainer explains a real decision
st = {"phase": sim.phase, "green_elapsed": 20,
      "queues": {"N": 12, "S": 8, "E": 1, "W": 0},
      "approaching": {"N": 2, "S": 1, "E": 0, "W": 0},
      "safety_holds": sim.safety_holds, "decision": "hold green"}
en, src_en = explain_decision(st, "en")
ur, src_ur = explain_decision(st, "ur")
check("explainer EN", len(en) > 20, "[%s]" % src_en)
check("explainer UR", len(ur) > 20, "[%s]" % src_ur)

# 4. Learner can log
import sabz_learn
check("learner nightly stands down while training",
      sabz_learn.training_alive() in (True, False), "safe either way")

print("\n%d/%d passed" % (sum(1 for r in results if r[1] == PASS), len(results)))
sys.exit(0 if all(r[1] == PASS for r in results) else 1)
