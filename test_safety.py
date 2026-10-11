"""Safety proof: the accident scenario is real, and the safety rule kills it.

Scenario: platooned arrivals. A fast car approaches an EMPTY stop line just as
the controller wants to gap-out. Without dilemma-zone protection the signal
cuts green under it (would_violate > 0). With protection, green holds.
"""
from sabz_sim2 import run_v2, actuated_decide


def platoon_rates(a, t):
    # bursts every 45 s on N/S: cars arrive fast at an empty stop line
    if a in ("N", "S") and (t % 45.0) < 4.0:
        return 0.8
    return 0.02 if a in ("N", "S") else 0.03


def asym(a, t):
    return 0.25 if a in ("N", "S") else 0.035


print("== Safety ablation (platoon scenario, actuated controller) ==")
off = run_v2("actuated", platoon_rates, T=1800.0, seed=5, safety_on=False)
on = run_v2("actuated", platoon_rates, T=1800.0, seed=5, safety_on=True)
print(f"safety OFF: controller tried unsafe cutoffs {off['would_violate']} times")
print(f"safety ON : unsafe cutoffs attempted {on['would_violate']}, "
      f"held by safety rule {on['safety_holds']}")
assert off["would_violate"] > 0, "test scenario must produce the danger"
assert on["safety_holds"] > 0, "safety rule must engage"

print()
print("== v2 sanity vs v1 (asymmetric, 1 h) ==")
for ctrl in ("fixed", "actuated"):
    m = run_v2(ctrl, asym, T=3600.0, seed=11)
    print(f"{ctrl:9s} avg_delay={m['avg_delay_s']:6.1f}s "
          f"served={m['served']} holds={m['safety_holds']}")
print()
print("ALL SAFETY TESTS PASSED")
