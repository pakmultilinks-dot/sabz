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

from sabz_rl import DQN, load_net, run_v2, state_vec_from_dict, \
    bench_scenarios, PROMO_SEEDS

BEST_FILE = os.path.join(HERE, "sabz_dqn_capable.npz")


def main():
    net = load_net(BEST_FILE)

    def rl_decide(state, prio):
        return "switch" if net.act(state_vec_from_dict(state)) == 1 \
            else "stay"

    wins = 0
    for name, rates in bench_scenarios().items():
        da, dd = [], []
        for sd in PROMO_SEEDS:
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
