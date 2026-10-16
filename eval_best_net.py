"""One-off honest benchmark of the TRUE best net (sabz_dqn_capable.npz).

train() renames sabz_dqn_best.npz into the output file at the end of each
block, so train_until_capable.bench() falls back to the checkpoint net
(latest, possibly degraded) instead of the best net. This script loads the
best net directly and runs the identical 3-scenario benchmark.
Read-only: does not touch training files or the running process.
"""
import os
import sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from sabz_rl import DQN, load_net, run_v2, state_vec_from_dict

BEST_FILE = os.path.join(HERE, "sabz_dqn_capable.npz")


def main():
    net = load_net(BEST_FILE)

    def rl_decide(state, prio):
        return "switch" if net.act(state_vec_from_dict(state)) == 1 \
            else "stay"

    scenarios = {
        "asymmetric": lambda a, t: 0.25 if a in ("N", "S") else 0.035,
        "balanced": lambda a, t: 0.22,
        "school": lambda a, t: (0.30 if a in ("N", "S") else 0.10)
        if 7 <= (t / 3600) % 24 <= 9 else 0.08,
    }
    wins = 0
    for name, rates in scenarios.items():
        da, dd = [], []
        for sd in (11, 22, 33):
            da.append(run_v2("actuated", rates, T=3600.0, seed=sd,
                             safety_on=True)["avg_delay_s"])
            dd.append(run_v2(rl_decide, rates, T=3600.0, seed=sd,
                            safety_on=True)["avg_delay_s"])
        ma, md = float(np.mean(da)), float(np.mean(dd))
        ok = md <= ma
        wins += ok
        print("  %-10s actuated %6.1fs | dqn-best %6.1fs | %s"
              % (name, ma, md, "WIN" if ok else "LOSE"), flush=True)
    print("BEST-NET BENCH: %d/3 scenarios won" % wins, flush=True)


if __name__ == "__main__":
    main()
