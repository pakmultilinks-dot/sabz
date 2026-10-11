"""SABZ brain training: our own DQN signal controller, trained from scratch.

This is the "train our own model" deliverable. A Deep Q-Network learns the
signal-timing policy inside the SABZ v2 simulator. Safety (dilemma-zone
protection) stays a HARD environment rule, so the network learns efficiency
only; it can never learn an unsafe cutoff.

State (10): queued vehicles per approach (/20), approaching vehicles in
camera range per approach (/10), current phase NS=1/EW=0, green elapsed /60.
Actions: 0 = hold green, 1 = switch phase. Reward: -queue/40 - 0.3*switch.
"""
import os
import numpy as np
from sabz_sim2 import (IntersectionV2, PHASES, MAX_GREEN, MIN_GREEN,
                       run_v2)

N_IN, N_H, N_OUT = 10, 64, 2
GAMMA = 0.97
LR = 1e-3
BUFFER = 30000
BATCH = 64
EPS0, EPS1, EPS_DECAY = 1.0, 0.05, 0.9995
TARGET_SYNC = 500
TRAIN_EVERY = 4


def get_state(sim):
    q = [len(sim.queue_of(a)) / 20.0 for a in ("N", "S", "E", "W")]
    ap = [len(sim.approaching(a)) / 10.0 for a in ("N", "S", "E", "W")]
    return np.array(q + ap + [1.0 if sim.phase == "NS" else 0.0,
                             sim.green_elapsed / MAX_GREEN],
                    dtype=np.float64)


class DQN:
    def __init__(self, seed=0):
        r = np.random.default_rng(seed)
        self.p = {
            "W1": r.normal(0, np.sqrt(2 / N_IN), (N_IN, N_H)),
            "b1": np.zeros(N_H),
            "W2": r.normal(0, np.sqrt(2 / N_H), (N_H, N_H)),
            "b2": np.zeros(N_H),
            "W3": r.normal(0, np.sqrt(2 / N_H), (N_H, N_OUT)),
            "b3": np.zeros(N_OUT),
        }
        self.m = {k: np.zeros_like(v) for k, v in self.p.items()}
        self.v = {k: np.zeros_like(v) for k, v in self.p.items()}
        self.t = 0

    def forward(self, x):
        z1 = x @ self.p["W1"] + self.p["b1"]
        a1 = np.maximum(z1, 0)
        z2 = a1 @ self.p["W2"] + self.p["b2"]
        a2 = np.maximum(z2, 0)
        q = a2 @ self.p["W3"] + self.p["b3"]
        return q, (x, z1, a1, z2, a2)

    def act(self, s):
        q, _ = self.forward(s)
        return int(np.argmax(q))

    def copy_from(self, other):
        for k in self.p:
            self.p[k] = other.p[k].copy()

    def train_batch(self, s, a, r, s2, done, target):
        self.t += 1
        q, (x, z1, a1, z2, a2) = self.forward(s)
        q2, _ = target.forward(s2)
        y = r + GAMMA * np.max(q2, axis=1) * (1 - done)
        n = s.shape[0]
        dq = np.zeros_like(q)
        dq[np.arange(n), a] = (q[np.arange(n), a] - y) / n
        # backprop
        dW3 = a2.T @ dq
        db3 = dq.sum(0)
        da2 = dq @ self.p["W3"].T
        dz2 = da2 * (z2 > 0)
        dW2 = a1.T @ dz2
        db2 = dz2.sum(0)
        da1 = dz2 @ self.p["W2"].T
        dz1 = da1 * (z1 > 0)
        dW1 = x.T @ dz1
        db1 = dz1.sum(0)
        g = {"W1": dW1, "b1": db1, "W2": dW2, "b2": db2,
             "W3": dW3, "b3": db3}
        # Adam
        b1, b2, eps = 0.9, 0.999, 1e-8
        for k in self.p:
            self.m[k] = b1 * self.m[k] + (1 - b1) * g[k]
            self.v[k] = b2 * self.v[k] + (1 - b2) * g[k] ** 2
            mh = self.m[k] / (1 - b1 ** self.t)
            vh = self.v[k] / (1 - b2 ** self.t)
            self.p[k] -= LR * mh / (np.sqrt(vh) + eps)
        return float(np.mean((q[np.arange(n), a] - y) ** 2))


def scenario_sampler(rng):
    r = rng.random()
    if r < 0.4:
        rates = lambda a, t: 0.25 if a in ("N", "S") else 0.035
        sched = None
    elif r < 0.7:
        rates = lambda a, t: 0.22
        sched = None
    else:
        rates = lambda a, t: 0.45 if (a == "N" and 300 <= t < 700) else 0.12
        sched = lambda t: "NS" if 300 <= t < 700 else None
    return rates, sched


def train(episodes=1200, T=900.0, out="sabz_dqn.npz", log_every=100):
    rng = np.random.default_rng(7)
    net, tgt = DQN(seed=1), DQN(seed=1)
    buf_s, buf_a, buf_r, buf_s2, buf_d = [], [], [], [], []
    eps = EPS0
    steps = 0
    ep_rewards = []
    for ep in range(episodes):
        rates, sched = scenario_sampler(rng)
        sim = IntersectionV2(seed=int(rng.integers(1e9)), safety_on=True)
        s = get_state(sim)
        ep_r = 0.0
        sw_before = 0
        while sim.t < T:
            a = int(rng.integers(2)) if rng.random() < eps \
                else net.act(s)
            sw0 = sim.switches
            sim.step(rates,
                     lambda st, pr: "switch" if a == 1 else "stay",
                     schedule=sched)
            switched = 1.0 if sim.switches > sw0 else 0.0
            qtot = sum(len(sim.queue_of(x)) for x in ("N", "S", "E", "W"))
            r = -qtot / 40.0 - 0.3 * switched
            s2 = get_state(sim)
            done = 1.0 if sim.t >= T else 0.0
            buf_s.append(s)
            buf_a.append(a)
            buf_r.append(r)
            buf_s2.append(s2)
            buf_d.append(done)
            if len(buf_s) > BUFFER:
                for b in (buf_s, buf_a, buf_r, buf_s2, buf_d):
                    b.pop(0)
            s = s2
            ep_r += r
            steps += 1
            if steps % TRAIN_EVERY == 0 and len(buf_s) >= BATCH:
                idx = rng.integers(len(buf_s), size=BATCH)
                net.train_batch(
                    np.array([buf_s[i] for i in idx]),
                    np.array([buf_a[i] for i in idx]),
                    np.array([buf_r[i] for i in idx]),
                    np.array([buf_s2[i] for i in idx]),
                    np.array([buf_d[i] for i in idx]), tgt)
            if steps % TARGET_SYNC == 0:
                tgt.copy_from(net)
        eps = max(EPS1, eps * (EPS_DECAY ** 1))
        ep_rewards.append(ep_r)
        if (ep + 1) % log_every == 0:
            print(f"ep {ep+1}/{episodes} eps={eps:.3f} "
                  f"avg_r(last {log_every})={np.mean(ep_rewards[-log_every:]):.1f}",
                  flush=True)
    np.savez(out, **{f"p_{k}": v for k, v in net.p.items()})
    print("saved", out)
    return out


def load_net(path):
    d = np.load(path)
    net = DQN()
    for k in net.p:
        net.p[k] = d[f"p_{k}"]
    return net


def evaluate(path, seeds=(11, 22, 33)):
    net = load_net(path)

    def rl_decide(state, prio):
        q = [state["queue"][a] / 20.0 for a in ("N", "S", "E", "W")]
        ap = [state["approaching"][a] / 10.0 for a in ("N", "S", "E", "W")]
        s = np.array(q + ap + [1.0 if state["phase"] == "NS" else 0.0,
                              state["green_elapsed"] / MAX_GREEN])
        return "switch" if net.act(s) == 1 else "stay"

    def asym(a, t):
        return 0.25 if a in ("N", "S") else 0.035

    def bal(a, t):
        return 0.22

    print(f"{'scenario':11s}{'controller':10s}{'avg_delay':>10s}"
          f"{'viol':>6s}")
    for name, rates in (("asymmetric", asym), ("balanced", bal)):
        for ctrl in ("actuated", rl_decide):
            ds, vv = [], 0
            for sd in seeds:
                m = run_v2(ctrl, rates, T=3600.0, seed=sd, safety_on=True)
                ds.append(m["avg_delay_s"])
                vv += m["would_violate"] - m["safety_holds"]
            cname = ctrl if isinstance(ctrl, str) else "sabz-dqn"
            print(f"{name:11s}{cname:10s}{np.mean(ds):>10.1f}{vv:>6d}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "eval":
        evaluate("sabz_dqn.npz")
    else:
        train()
