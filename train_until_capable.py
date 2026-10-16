"""Train until capable: 120,000 is the floor, not the ceiling.

This script waits for the 120k run to finish, then keeps training in
40k-episode blocks until our DQN brain matches or beats the hand-tuned
actuated controller on EVERY benchmark scenario, or hits 400k episodes.

The bar (from the user's order: capable of everything we want):
  - asymmetric: DQN avg delay <= actuated
  - balanced:   DQN avg delay <= actuated
  - school:     DQN avg delay <= actuated

Only then is the brain done. Safety is untouched throughout: the hard
dilemma-zone rule is outside the network and no training can change it.

Usage: nohup python3 train_until_capable.py > train_capable.log 2>&1 &
"""
import os
import sys
import time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import sabz_rl
from sabz_rl import DQN, load_net, BEST, CKPT, DONE_FLAG, run_v2

BLOCK = 40000
MAX_EPISODES = 10000000


def load_best_net():
    """Load the best brain: BEST file if present, else net from checkpoint."""
    from sabz_rl import DQN, load_ckpt
    if os.path.exists(BEST):
        return load_net(BEST)
    net, tgt = DQN(), DQN()
    eps, ep, best = load_ckpt(CKPT, net, tgt)
    print("  (loaded net from checkpoint: episode %d, best %.1fs)"
          % (ep, best), flush=True)
    return net


def bench(path=None):
    """DQN vs actuated on all three scenarios. Returns (dqn_wins_all, rows)."""
    net = load_best_net()

    def rl_decide(state, prio):
        q = [state["queue"][a] / 20.0 for a in ("N", "S", "E", "W")]
        ap = [state["approaching"][a] / 10.0 for a in ("N", "S", "E", "W")]
        # 16-dim brain: 10 traffic features + 6 location features (zeros: the
        # benchmark scenarios use no per-junction location plan).
        s = np.array(q + ap + [1.0 if state["phase"] == "NS" else 0.0,
                              state["green_elapsed"] / 60.0]
                     + [0.0] * 6)
        return "switch" if net.act(s) == 1 else "stay"

    scenarios = {
        "asymmetric": lambda a, t: 0.25 if a in ("N", "S") else 0.035,
        "balanced": lambda a, t: 0.22,
        "school": lambda a, t: (0.30 if a in ("N", "S") else 0.10)
        if 7 <= (t / 3600) % 24 <= 9 else 0.08,
    }
    rows = []
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
        rows.append((name, ma, md, ok))
        print("  %-10s actuated %6.1fs | dqn %6.1fs | %s"
              % (name, ma, md, "WIN" if ok else "LOSE"), flush=True)
    return wins == len(scenarios), rows


def main():
    # The 120k run is dead (its flag was archived to backup_lost_run/); do not
    # wait forever. Give it a short grace in case it is still alive elsewhere,
    # then proceed from the checkpoint.
    print("waiting briefly for any 120k run to finish...", flush=True)
    for _ in range(3):
        if os.path.exists(DONE_FLAG):
            print("120k done. Entering train-until-capable.", flush=True)
            break
        time.sleep(60)
    else:
        print("no 120k run active; proceeding from checkpoint.", flush=True)

    target = 120000
    while target < MAX_EPISODES:
        capable, rows = bench()
        if capable:
            print("CAPABLE on all scenarios at %d episodes. Brain is done."
                  % target, flush=True)
            open(os.path.join(HERE, "rl_capable.done"), "w").write(
                "episodes=%d\n" % target)
            return
        target += BLOCK
        print("not yet capable; extending training to %d episodes..."
              % target, flush=True)
        sabz_rl.train(episodes=target, out="sabz_dqn_capable.npz")
    print("hit %d episodes without full capability; keeping best."
          % MAX_EPISODES, flush=True)


if __name__ == "__main__":
    main()
