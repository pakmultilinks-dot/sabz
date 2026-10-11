"""v2 full evaluation: 3 scenarios x fixed/actuated x 3 seeds."""
from sabz_sim2 import run_v2

SEEDS = [11, 22, 33]


def asym(a, t):
    return 0.25 if a in ("N", "S") else 0.035


def balanced(a, t):
    return 0.22


def school_rates(a, t):
    if a == "N" and 1800.0 <= t < 3600.0:
        return 0.45
    return 0.12


def school_sched(t):
    tod = 7.0 + t / 3600.0
    return "NS" if 7.5 <= tod <= 8.5 else None


SCEN = {"asymmetric": (asym, None),
        "school": (school_rates, school_sched),
        "balanced": (balanced, None)}

for name, (rates, sched) in SCEN.items():
    line = f"{name:11s}"
    for ctrl in ("fixed", "actuated"):
        ds, holds = [], 0
        for s in SEEDS:
            m = run_v2(ctrl, rates, schedule=sched, T=3600.0, seed=s)
            ds.append(m["avg_delay_s"])
            holds += m["safety_holds"]
        avg = sum(ds) / len(ds)
        line += f" | {ctrl}: delay={avg:5.1f}s holds={holds}"
    print(line)
