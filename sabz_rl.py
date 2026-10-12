"""SABZ brain training: our own DQN signal controller, trained from scratch.

This is the "train our own model" deliverable. A Deep Q-Network learns the
signal-timing policy inside the SABZ v2 simulator. Safety (dilemma-zone
protection) stays a HARD environment rule, so the network learns efficiency
only; it can never learn an unsafe cutoff.

State (16): queued vehicles per approach (/20), approaching vehicles in
camera range per approach (/10), current phase NS=1/EW=0, green elapsed /60,
plus 6 LOCATION features the brain uses to understand where it is:
near_school, near_mosque, near_office, near_hospital (0/1),
is_friday (0/1 for Jummah), hour_of_day (/24).
Actions: 0 = hold green, 1 = switch phase. Reward: -queue/40 - 0.3*switch.
"""
import os
import numpy as np
from sabz_sim2 import (IntersectionV2, PHASES, MAX_GREEN, MIN_GREEN,
                       run_v2)

N_POI = 6  # location features: school, mosque, office, hospital, friday, hour
N_IN, N_H, N_OUT = 10 + N_POI, 64, 2
GAMMA = 0.97
LR = 1e-3
BUFFER = 30000
BATCH = 64
EPS0, EPS1, EPS_DECAY = 1.0, 0.05, 0.9995
TARGET_SYNC = 500
TRAIN_EVERY = 4


def get_state(sim, loc=None):
    q = [len(sim.queue_of(a)) / 20.0 for a in ("N", "S", "E", "W")]
    ap = [len(sim.approaching(a)) / 10.0 for a in ("N", "S", "E", "W")]
    base = q + ap + [1.0 if sim.phase == "NS" else 0.0,
                     sim.green_elapsed / MAX_GREEN]
    if loc is None:
        loc = [0.0] * N_POI
    return np.array(base + list(loc), dtype=np.float64)


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


CKPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "sabz_dqn_ckpt.npz")
BEST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "sabz_dqn_best.npz")
DONE_FLAG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "rl_train.done")


def save_ckpt(path, net, tgt, eps, episode, best_score):
    d = {f"net_{k}": v for k, v in net.p.items()}
    d.update({f"tgt_{k}": v for k, v in tgt.p.items()})
    d.update({f"m_{k}": v for k, v in net.m.items()})
    d.update({f"v_{k}": v for k, v in net.v.items()})
    d["adam_t"] = np.array([net.t])
    d["eps"] = np.array([eps])
    d["episode"] = np.array([episode])
    d["best_score"] = np.array([best_score])
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        np.savez(f, **d)
    os.replace(tmp, path)


def load_ckpt(path, net, tgt):
    d = np.load(path)
    for k in net.p:
        old_net = d[f"net_{k}"]
        old_tgt = d[f"tgt_{k}"]
        if k == "W1" and old_net.shape[0] != net.p[k].shape[0]:
            # TRANSFER: old brain had 10 inputs, new has 16 (10 + 6 location).
            # Keep learned weights for the 10 traffic features, init the 6
            # location weights small so the brain starts as its old self.
            print(f"transfer: expanding W1 {old_net.shape} -> {net.p[k].shape}",
                  flush=True)
            new_w = np.random.default_rng(0).normal(
                0, 0.01, net.p[k].shape)
            new_w[:old_net.shape[0], :] = old_net
            net.p[k] = new_w
            new_wt = np.random.default_rng(1).normal(
                0, 0.01, tgt.p[k].shape)
            new_wt[:old_tgt.shape[0], :] = old_tgt
            tgt.p[k] = new_wt
            # Adam state for W1: keep old, zero-init the new rows
            for arr, name in ((net.m, "m"), (net.v, "v")):
                old_a = d[f"{name}_{k}"]
                nw = np.zeros_like(net.p[k])
                nw[:old_a.shape[0], :] = old_a
                arr[k] = nw
        else:
            net.p[k] = old_net
            tgt.p[k] = old_tgt
            net.m[k] = d[f"m_{k}"]
            net.v[k] = d[f"v_{k}"]
    net.t = int(d["adam_t"][0])
    return float(d["eps"][0]), int(d["episode"][0]), float(d["best_score"][0])


def quick_eval(net):
    """Greedy policy score: mean delay, lower is better. Fast eval."""
    def rl_decide(state, prio):
        q = [state["queue"][a] / 20.0 for a in ("N", "S", "E", "W")]
        ap = [state["approaching"][a] / 10.0 for a in ("N", "S", "E", "W")]
        s = np.array(q + ap + [1.0 if state["phase"] == "NS" else 0.0,
                              state["green_elapsed"] / MAX_GREEN]
                     + [0.0] * N_POI)
        return "switch" if net.act(s) == 1 else "stay"

    def asym(a, t):
        return 0.25 if a in ("N", "S") else 0.035

    def bal(a, t):
        return 0.22

    ds = []
    for rates in (asym, bal):
        for sd in (11, 22):
            m = run_v2(rl_decide, rates, T=1800.0, seed=sd, safety_on=True)
            ds.append(m["avg_delay_s"])
    return float(np.mean(ds))


def bc_pretrain(net, episodes=300, T=900.0, lr=3e-3, batch=256):
    """Behavioral cloning: teach the net to imitate the actuated controller.

    Gives our network a strong, sensible starting policy in minutes.
    DQN then refines it further. (Supervised cross-entropy on the Q-head
    treated as logits.)
    """
    from sabz_sim2 import actuated_decide
    rng = np.random.default_rng(11)
    Xs, Ys = [], []
    for ep in range(episodes):
        rates, sched, loc = scenario_sampler(rng)
        sim = IntersectionV2(seed=int(rng.integers(1e9)), safety_on=True)
        s = get_state(sim, loc)
        while sim.t < T:
            st = {"t": sim.t, "phase": sim.phase,
                  "green_elapsed": sim.green_elapsed,
                  "queue": {a: len(sim.queue_of(a)) for a in
                            ("N", "S", "E", "W")},
                  "approaching": {a: len(sim.approaching(a)) for a in
                                  ("N", "S", "E", "W")},
                  "dilemma": sim.dilemma(), "obs": sim.observe()}
            a = 1 if actuated_decide(st, sched(sim.t) if sched else None) \
                == "switch" else 0
            # small exploration so the net sees off-policy states too
            if rng.random() < 0.15:
                a = int(rng.integers(2))
            Xs.append(s)
            Ys.append(a)
            sim.step(rates,
                     lambda st2, pr: "switch" if a == 1 else "stay",
                     schedule=sched)
            s = get_state(sim, loc)
    X = np.array(Xs)
    Y = np.array(Ys)
    n = len(X)
    # Adam from scratch for the supervised phase
    m = {k: np.zeros_like(v) for k, v in net.p.items()}
    v = {k: np.zeros_like(v) for k, v in net.p.items()}
    for step in range(1, 2001):
        idx = rng.integers(n, size=batch)
        xb, yb = X[idx], Y[idx]
        q, (x, z1, a1, z2, a2) = net.forward(xb)
        e = np.exp(q - q.max(1, keepdims=True))
        p = e / e.sum(1, keepdims=True)
        loss = -np.log(p[np.arange(batch), yb] + 1e-12).mean()
        dq = p
        dq[np.arange(batch), yb] -= 1
        dq /= batch
        dW3 = a2.T @ dq
        db3 = dq.sum(0)
        dz2 = (dq @ net.p["W3"].T) * (z2 > 0)
        dW2 = a1.T @ dz2
        db2 = dz2.sum(0)
        dz1 = (dz2 @ net.p["W2"].T) * (z1 > 0)
        dW1 = x.T @ dz1
        db1 = dz1.sum(0)
        g = {"W1": dW1, "b1": db1, "W2": dW2, "b2": db2,
             "W3": dW3, "b3": db3}
        b1, b2, eps_ = 0.9, 0.999, 1e-8
        for k in net.p:
            m[k] = b1 * m[k] + (1 - b1) * g[k]
            v[k] = b2 * v[k] + (1 - b2) * g[k] ** 2
            net.p[k] -= lr * (m[k] / (1 - b1 ** step)) / (
                np.sqrt(v[k] / (1 - b2 ** step)) + eps_)
        if step % 500 == 0:
            pred = net.forward(X[:2000])[0].argmax(1)
            acc = (pred == Y[:2000]).mean()
            print(f"bc step {step} loss={loss:.3f} acc={acc:.3f}", flush=True)
    return net


def scenario_sampler(rng):
    import real_traffic as rt
    hour = int(rng.integers(0, 24))
    # LOCATION: sample what kind of place this intersection is.
    # The brain sees these 6 features and learns location-aware control.
    loc_r = rng.random()
    if loc_r < 0.22:
        # Near school: sharp morning drop-off / afternoon pickup rush
        loc = [1.0, 0.0, 0.0, 0.0, 0.0, hour / 24.0]
        base = rt.arrival_rate(8)
        rates = lambda a, t: base * 1.8 if (a == "N" and 300 <= t < 700) else base * 0.5
        sched = lambda t: "NS" if 300 <= t < 700 else None
    elif loc_r < 0.42:
        # Near mosque: Friday Jummah 12:00-14:30 surge
        is_fri = 1.0 if rng.random() < 0.18 else 0.0
        loc = [0.0, 1.0, 0.0, 0.0, is_fri, hour / 24.0]
        jummah = is_fri and 12 <= hour <= 14
        base = rt.arrival_rate(13) if jummah else rt.arrival_rate(hour)
        mult = 2.2 if jummah else 1.0
        rates = lambda a, t, m=mult, b=base: b * m
        sched = None
    elif loc_r < 0.62:
        # Near office: 9-5 commuter tidal flow
        loc = [0.0, 0.0, 1.0, 0.0, 0.0, hour / 24.0]
        base = rt.arrival_rate(hour)
        rates = lambda a, t, b=base: b * 1.6 if a in ("N", "S") else b * 0.4
        sched = None
    elif loc_r < 0.75:
        # Near hospital: steady flow, all approaches matter
        loc = [0.0, 0.0, 0.0, 1.0, 0.0, hour / 24.0]
        base = rt.arrival_rate(hour)
        rates = lambda a, t, b=base: b * 1.15
        sched = None
    elif loc_r < 0.82:
        # ACCIDENT: one approach blocked, brain must reroute green
        blocked = rng.choice(["N", "S", "E", "W"])
        loc = [0.0, 0.0, 0.0, 0.0, 0.0, hour / 24.0]
        base = rt.arrival_rate(hour)
        rates = lambda a, t, b=base, blk=blocked: 0.0 if a == blk else b * 1.3
        sched = None
    elif loc_r < 0.88:
        # EMERGENCY: sudden priority surge on one approach
        emerg = rng.choice(["N", "S", "E", "W"])
        loc = [0.0, 0.0, 0.0, 1.0, 0.0, hour / 24.0]
        base = rt.arrival_rate(hour)
        rates = lambda a, t, b=base, em=emerg: b * 3.0 if (a == em and 200 <= t < 500) else b
        sched = None
    elif loc_r < 0.94:
        # NIGHT: very low traffic, brain must not waste green
        loc = [0.0, 0.0, 0.0, 0.0, 0.0, 2 / 24.0]
        base = rt.arrival_rate(2) * 0.3
        rates = lambda a, t, b=base: b
        sched = None
    elif loc_r < 0.96:
        # CRISIS COMPOUND: accident during rush hour, chaos
        blocked = rng.choice(["N", "S", "E", "W"])
        loc = [1.0, 0.0, 0.0, 0.0, 0.0, 8 / 24.0]
        base = rt.arrival_rate(8) * 1.5
        rates = lambda a, t, b=base, blk=blocked: 0.0 if a == blk else b * (1.5 + 0.5 * np.sin(t / 100))
        sched = None
    elif loc_r < 0.98:
        # STADIUM EVENT: massive surge then sudden drop
        loc = [0.0, 0.0, 1.0, 0.0, 0.0, 20 / 24.0]
        base = rt.arrival_rate(20)
        rates = lambda a, t, b=base: b * 4.0 if 100 <= t < 400 else b * 0.2
        sched = None
    else:
        # Generic junction (original calibrated patterns)
        loc = [0.0, 0.0, 0.0, 0.0, 0.0, hour / 24.0]
        r = rng.random()
        if r < 0.4:
            base = rt.arrival_rate(hour)
            rates = lambda a, t, b=base: b * 1.6 if a in ("N", "S") else b * 0.25
            sched = None
        elif r < 0.7:
            base = rt.arrival_rate(hour)
            rates = lambda a, t, b=base: b
            sched = None
        else:
            base = rt.arrival_rate(8)
            rates = lambda a, t, b=base: b * 1.8 if (a == "N" and 300 <= t < 700) else b * 0.5
            sched = lambda t: "NS" if 300 <= t < 700 else None
    return rates, sched, loc


def train(episodes=120000, T=900.0, out="sabz_dqn.npz", log_every=100,
          ckpt_every=500, eval_every=2000):
    rng = np.random.default_rng(7)
    net, tgt = DQN(seed=1), DQN(seed=1)
    eps, start_ep, best_score = EPS0, 0, 1e9
    if os.path.exists(CKPT):
        eps, start_ep, best_score = load_ckpt(CKPT, net, tgt)
        print(f"resumed from episode {start_ep} (eps={eps:.3f}, "
              f"best={best_score:.1f}s)", flush=True)
    buf_s, buf_a, buf_r, buf_s2, buf_d = [], [], [], [], []
    steps = 0
    ep_rewards = []
    for ep in range(start_ep, episodes):
        rates, sched, loc = scenario_sampler(rng)
        sim = IntersectionV2(seed=int(rng.integers(1e9)), safety_on=True)
        s = get_state(sim, loc)
        ep_r = 0.0
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
            s2 = get_state(sim, loc)
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
        eps = max(EPS1, eps * EPS_DECAY)
        ep_rewards.append(ep_r)
        done_ep = ep + 1
        if done_ep % ckpt_every == 0:
            save_ckpt(CKPT, net, tgt, eps, done_ep, best_score)
        if done_ep % eval_every == 0:
            score = quick_eval(net)
            if score < best_score:
                best_score = score
                np.savez(BEST, **{f"p_{k}": v for k, v in net.p.items()})
                print(f"ep {done_ep}: NEW BEST eval delay {score:.1f}s",
                      flush=True)
            save_ckpt(CKPT, net, tgt, eps, done_ep, best_score)
        if done_ep % log_every == 0:
            print(f"ep {done_ep}/{episodes} eps={eps:.3f} "
                  f"avg_r(last {log_every})={np.mean(ep_rewards[-log_every:]):.1f} "
                  f"best={best_score:.1f}s", flush=True)
    np.savez(out, **{f"p_{k}": v for k, v in net.p.items()})
    if os.path.exists(BEST):
        os.replace(BEST, out)
    open(DONE_FLAG, "w").write(f"episodes={episodes}\n")
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
                              state["green_elapsed"] / MAX_GREEN]
                     + [0.0] * N_POI)
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
    elif len(sys.argv) > 1 and sys.argv[1] == "bc":
        net = DQN(seed=1)
        bc_pretrain(net)
        np.savez("sabz_dqn_bc.npz",
                 **{f"p_{k}": v for k, v in net.p.items()})
        tgt = DQN(seed=1)
        tgt.copy_from(net)
        save_ckpt(CKPT, net, tgt, 0.3, 0, 1e9)
        print("BC done; checkpoint seeded for DQN refinement")
    else:
        # Speed mode: shorter episodes for 2x training throughput
        train(T=200.0)
