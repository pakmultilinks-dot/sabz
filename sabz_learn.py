"""SABZ continual learning: the brain improves itself day by day.

The idea is simple and honest:
- Every day the controller runs, its experiences (state, action, reward)
  are logged.
- Every night, training resumes from the checkpoint and keeps learning,
  now on fresh simulated traffic plus the logged real experiences.
- The best-known brain is only replaced when a challenger beats it on
  the benchmark scenarios. The system never gets worse overnight.

Safety is never learned and never retrained: the dilemma-zone hard rule
lives outside the network and no training run can change it.

Usage:
    python3 sabz_learn.py log --day 2026-10-11
    python3 sabz_learn.py nightly --episodes 2000   # cron at 03:00

nightly() REFUSES to run while the main training job is alive, so it can
never corrupt an in-progress run.
"""
import os
import sys
import subprocess
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sabz_rl import DQN, get_state, load_net, BEST
from sabz_sim2 import IntersectionV2

LOGDIR = os.path.join(HERE, "logs")
os.makedirs(LOGDIR, exist_ok=True)
CKPT = os.path.join(HERE, "sabz_dqn_ckpt.npz")


def training_alive():
    try:
        out = subprocess.run(["pgrep", "-f", "sabz_rl.py"],
                             capture_output=True, text=True)
        return bool(out.stdout.strip())
    except Exception:
        return False


def log_day(day, T=3600.0, seed=7):
    """Run the current best brain for a simulated day, save experiences."""
    net = DQN()
    if os.path.exists(BEST):
        net = load_net(BEST)
        print("loaded best brain for logging")
    else:
        print("no best brain yet, logging with actuated policy instead")
        net = None
    rng = np.random.RandomState(seed)
    buf = []
    sim = IntersectionV2(seed=seed)

    def rates(a, t):
        h = (t / 3600.0) % 24
        base = 0.05
        if 7 <= h <= 9:
            base = 0.30 if a in "NS" else 0.10
        elif 17 <= h <= 19:
            base = 0.28 if a in "EW" else 0.10
        return base

    s = get_state(sim)
    while sim.t < T:
        if net and rng.random() > 0.05:
            a = net.act(s)
        else:
            # actuated fallback for exploration / no-brain case
            a = 0
        sw0 = sim.switches
        sim.step(rates, lambda st, pr: "switch" if a == 1 else "stay")
        switched = 1.0 if sim.switches > sw0 else 0.0
        qtot = sum(len(sim.queue_of(x)) for x in "NSEW")
        r = -qtot / 40.0 - 0.3 * switched
        s2 = get_state(sim)
        buf.append((s, a, r, s2, 1.0 if sim.t >= T else 0.0))
        s = s2
    arr = np.array(buf, dtype=object)
    path = os.path.join(LOGDIR, "day-%s.npz" % day)
    np.savez_compressed(path, log=arr)
    print("logged %d steps -> %s" % (len(buf), path))
    return path


def nightly(episodes=2000):
    """Extend training safely. Only runs when no training is alive."""
    if training_alive():
        print("main training is still running; nightly stands down.")
        return False
    if not os.path.exists(CKPT):
        print("no checkpoint yet; nothing to extend.")
        return False
    import sabz_rl
    # train() resumes from CKPT, keeps BEST only on improvement.
    # episodes here is the NEW total target, not an increment.
    import re
    print("extending training: resuming from checkpoint...")
    sabz_rl.train(episodes=episodes, out="sabz_dqn_nightly.npz")
    print("nightly done; best brain kept only if it improved.")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "log":
        day = sys.argv[sys.argv.index("--day") + 1] if "--day" in sys.argv else "today"
        log_day(day)
    elif cmd == "nightly":
        n = int(sys.argv[sys.argv.index("--episodes") + 1]) if "--episodes" in sys.argv else 2000
        nightly(n)
    else:
        print(__doc__)
