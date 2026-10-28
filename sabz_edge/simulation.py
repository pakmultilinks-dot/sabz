"""Reproducible finite-storage, two-phase point-queue benchmark.

Synthetic traffic, ideal detector observations, no turns/pedestrians/collisions.
Every controller receives exactly the same pre-generated arrival stream and
uses the real SABZ safety kernel and cabinet guard under virtual time.
"""
from collections import deque
import hashlib
import json
import math
import random

from .core import APPROACHES, Controller, Observation, Timing, number
from .cabinet_model import Guard

DT = .25
SCENARIOS = {
    "tidal": {"name": "Tidal commute", "description": "Heavy northâ€“south demand changes to eastâ€“west halfway through."},
    "balanced": {"name": "Balanced demand", "description": "Similar demand on all approaches; a useful fixed-plan comparison."},
    "bursts": {"name": "Platoons & gaps", "description": "Short arrival platoons separated by quiet periods."},
    "spillback": {"name": "Downstream blockage", "description": "Northâ€“south receiving links are externally filled from 100 to 220 seconds."},
    "night": {"name": "Quiet side street", "description": "Low northâ€“south demand and sparse eastâ€“west arrivals."},
    "sensor": {"name": "Camera loss", "description": "Observation updates stop from 100 to 120 seconds."},
    "school": {"name": "School-like surge", "description": "A synthetic north approach surge from 70 to 180 seconds."},
}


def rates(scenario, t, duration):
    if scenario == "tidal":
        return (.32, .28, .035, .04) if t < duration / 2 else (.035, .04, .32, .28)
    if scenario == "balanced":
        return (.18,) * 4
    if scenario == "bursts":
        return ((.65, .55, .02, .02) if t % 70 < 12 else
                ((.02, .02, .6, .5) if 35 <= t % 70 < 47 else (.015,) * 4))
    if scenario == "night":
        return (.045, .035, .01, .008)
    if scenario == "school":
        return (.6, .11, .08, .08) if 70 <= t < 180 else (.08,) * 4
    return (.2, .18, .15, .13)


def arrival_stream(scenario, seed, duration, demand_scale=1.0):
    if scenario not in SCENARIOS:
        raise ValueError("unknown scenario")
    rng = random.Random(seed)
    stream = []
    # Poisson counts per fixed tick, generated without controller state.
    for step in range(int(duration / DT)):
        t = step * DT
        for i, rate in enumerate(rates(scenario, t, duration)):
            limit, product, count = math.exp(-rate * demand_scale * DT), 1.0, 0
            while product > limit:
                product *= rng.random()
                count += 1
            for _ in range(count - 1):
                stream.append((round(t + rng.random() * DT, 5), i))
    return sorted(stream)


def simulate(scenario="tidal", seed=17, duration=360, mode="adaptive", stream=None, trace=True, demand_scale=1.0):
    if duration < 30 or duration > 3600 or duration % DT:
        raise ValueError("duration must be 30..3600 seconds in quarter-second steps")
    number(demand_scale, "demand_scale", .5, 1.5)
    stream = arrival_stream(scenario, seed, duration, demand_scale) if stream is None else stream
    fingerprint = hashlib.sha256(json.dumps(stream, separators=(",", ":")).encode()).hexdigest()
    timing = Timing()
    controller, cabinet = Controller(timing, 0, mode=mode), Guard(timing, 0)
    queues = [deque() for _ in APPROACHES]
    inbound = [deque() for _ in APPROACHES]
    recent = [deque() for _ in APPROACHES]
    down = [0.] * 4
    capacity = [20.] * 4
    next_depart = [0.] * 4
    arrived = served = pos = 0
    accrued_delay = maximum_wait = 0.
    completed_waits = []
    last_obs = received = None
    frames = []
    yellow_transitions = 0
    last_stage = "ALL_RED"
    for step in range(int(duration / DT) + 1):
        t = step * DT
        while pos < len(stream) and stream[pos][0] <= t:
            spawned, approach = stream[pos]
            arrived += 1
            inbound[approach].append((spawned + 8, arrived))
            recent[approach].append(spawned)
            pos += 1
        for i in range(4):
            while inbound[i] and inbound[i][0][0] <= t:
                queues[i].append(inbound[i].popleft())
            while recent[i] and recent[i][0] < t - 30:
                recent[i].popleft()
            if scenario == "spillback" and i < 2 and 100 <= t < 220:
                down[i] = capacity[i]  # Exogenous receiving-road occupancy.
            else:
                down[i] = max(0., down[i] - .65 * DT)
        packet = {"schema_version": 2, "sequence": step, "captured_at": 1e9 + t,
                  "counts": {a: min(100, len(queues[i])) for i, a in enumerate(APPROACHES)},
                  "conflict_clear": True, "healthy": True,
                  "downstream_counts": dict(zip(APPROACHES, down)),
                  "downstream_capacity": dict(zip(APPROACHES, capacity)),
                  "approaching": {a: sum(eta - t <= 4 for eta, _ in inbound[i]) for i, a in enumerate(APPROACHES)},
                  "arrival_rate": {a: len(recent[i]) / 30 for i, a in enumerate(APPROACHES)},
                  "oldest_wait_s": {a: t - queues[i][0][0] if queues[i] else 0 for i, a in enumerate(APPROACHES)}}
        if not (scenario == "sensor" and 100 <= t < 120):
            last_obs, received = Observation.parse(packet, 1e9 + t), t
        intent = controller.tick(t, last_obs, received)
        actual = cabinet.accept(dict(intent, command_sequence=step, lease_s=.5), t)
        if (any(actual["lamps"][a] != "RED" for a in "NS")
                and any(actual["lamps"][a] != "RED" for a in "EW")):
            raise RuntimeError("conflicting virtual cabinet outputs")
        if actual["fault"]:
            raise RuntimeError(f"unexpected virtual cabinet fault: {actual['fault']}")
        if actual["stage"] == "YELLOW" and last_stage != "YELLOW":
            yellow_transitions += 1
        last_stage = actual["stage"]
        for i, a in enumerate(APPROACHES):
            if actual["lamps"][a] != "GREEN":
                next_depart[i] = t + 1.0
            elif queues[i] and down[i] + 1 <= capacity[i] and t >= next_depart[i]:
                stopline_t, _ = queues[i].popleft()
                wait = max(0, t - stopline_t)
                completed_waits.append(wait)
                maximum_wait = max(maximum_wait, wait)
                served += 1
                down[i] += 1
                next_depart[i] = t + 2.0
        if step < int(duration / DT):
            accrued_delay += sum(map(len, queues)) * DT
        maximum_wait = max([maximum_wait] + [t - q[0][0] for q in queues if q])
        if trace and step % 4 == 0:
            frames.append({"t": t, "queues": list(map(len, queues)), "approaching": list(map(len, inbound)),
                           "downstream": [round(v, 2) for v in down], "capacity": capacity[:],
                           "lamps": actual["lamps"], "stage": actual["stage"], "phase": actual["phase"],
                           "reason": intent["reason"], "scores": intent["phase_scores"],
                           "arrived": arrived, "served": served, "delay_s": round(accrued_delay, 2),
                           "mean_delay_s": round(accrued_delay / max(arrived, 1), 3),
                           "max_wait_s": round(maximum_wait, 2), "sensor_ok": not (scenario == "sensor" and 100 <= t < 120)})
    remaining = sum(map(len, queues)) + sum(map(len, inbound))
    assert arrived == served + remaining, "vehicle conservation failed"
    waits = sorted(completed_waits)
    return {"scenario": scenario, "seed": seed, "duration_s": duration, "controller": mode, "demand_scale": demand_scale,
            "arrival_sha256": fingerprint, "arrived": arrived, "served": served,
            "unfinished": remaining, "accrued_delay_s": round(accrued_delay, 3),
            "mean_delay_s": round(accrued_delay / max(arrived, 1), 3),
            "p95_completed_wait_s": round(waits[min(len(waits) - 1, int(.95 * len(waits)))], 3) if waits else None,
            "max_observed_wait_s": round(maximum_wait, 3), "changes": yellow_transitions,
            "frames": frames}
