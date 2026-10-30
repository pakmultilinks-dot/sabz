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
from .coordination import Coordinator

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
            "p99_completed_wait_s": round(waits[min(len(waits) - 1, int(.99 * len(waits)))], 3) if waits else None,
            "max_observed_wait_s": round(maximum_wait, 3), "changes": yellow_transitions,
            "frames": frames}


# ---------------------------------------------------------------------------
# Two-intersection corridor: I0 feeds I1 through a finite link.  Vehicles
# enter at I0's south approach, cross I0, travel the link, cross I1 and exit.
# Cross traffic at each intersection is local.  The same safety kernel and
# cabinet guard run at both nodes; the Coordinator only supplies offsets,
# the green-wave preference and downstream supply hints.

LINK_TRAVEL_S = 20.0
APPROACH_TRAVEL_S = 8.0
CORRIDOR_RATES = {
    # (intersection, approach index): vehicles/second
    ("I0", 1): .26,   # southbound entry, the main platoon (below signal capacity)
    ("I0", 0): .02,   # local north approach, exits at I0
    ("I0", 2): .05, ("I0", 3): .05,
    ("I1", 1): .16,   # corridor through-traffic plus local south approach
    ("I1", 0): .02,
    ("I1", 2): .05, ("I1", 3): .05,
}


def corridor_stream(seed, duration, demand_scale=1.0):
    rng = random.Random(seed)
    stream = []
    for step in range(int(duration / DT)):
        t = step * DT
        for (intersection, approach), rate in CORRIDOR_RATES.items():
            limit, product, count = math.exp(-rate * demand_scale * DT), 1.0, 0
            while product > limit:
                product *= rng.random()
                count += 1
            for _ in range(count - 1):
                stream.append((round(t + rng.random() * DT, 5), intersection, approach))
    return sorted(stream)


def simulate_corridor(seed=17, duration=360, mode="max_pressure", coordinated=True,
                      stream=None, trace=False, demand_scale=1.0, offset_s=None):
    if duration < 30 or duration > 3600 or duration % DT:
        raise ValueError("duration must be 30..3600 seconds in quarter-second steps")
    number(demand_scale, "demand_scale", .5, 1.5)
    stream = corridor_stream(seed, duration, demand_scale) if stream is None else stream
    fingerprint = hashlib.sha256(json.dumps(stream, separators=(",", ":")).encode()).hexdigest()
    timing = Timing()
    off = LINK_TRAVEL_S if offset_s is None else float(offset_s)
    coordinator = Coordinator(offsets={"I0": 0.0, "I1": off if coordinated else 0.0},
                              cycle_s=80.0,
                              links=[("I0", "I1", LINK_TRAVEL_S)]) if coordinated else None
    nodes = {}
    for name in ("I0", "I1"):
        nodes[name] = {
            "controller": Controller(timing, 0, mode=mode, coordinator=coordinator, intersection=name),
            "cabinet": Guard(timing, 0),
            "queues": [deque() for _ in APPROACHES],
            "inbound": [deque() for _ in APPROACHES],
            "recent": [deque() for _ in APPROACHES],
            "down": [0.] * 4,
            "next_depart": [0.] * 4,
            "last_obs": None, "received": None,
        }
    link = deque()          # (arrival_time_at_I1, release_time_at_I0, spawn_time, vehicle_id)
    arrived = exited = pos = 0
    accrued_delay = maximum_wait = 0.
    completed_waits = []
    last_stage = {n: "ALL_RED" for n in nodes}
    last_lamps = {n: dict.fromkeys(APPROACHES, "RED") for n in nodes}
    last_reason = {n: None for n in nodes}
    yellow_transitions = 0
    frames = []
    for step in range(int(duration / DT) + 1):
        t = step * DT
        while pos < len(stream) and stream[pos][0] <= t:
            spawned, intersection, approach = stream[pos]
            arrived += 1
            nodes[intersection]["inbound"][approach].append((spawned + APPROACH_TRAVEL_S, spawned, arrived))
            pos += 1
        # Link vehicles finish travel and join I1's south queue.
        while link and link[0][0] <= t:
            _, released, spawn, vid = link.popleft()
            if coordinator is not None:
                coordinator.note_arrival("I0", "I1", released, t)
            nodes["I1"]["queues"][1].append((t, spawn, vid))
        for name, node in nodes.items():
            for i in range(4):
                while node["inbound"][i] and node["inbound"][i][0][0] <= t:
                    node["queues"][i].append(node["inbound"][i].popleft())
                while node["recent"][i] and node["recent"][i][0] < t - 30:
                    node["recent"][i].popleft()
                node["down"][i] = max(0., node["down"][i] - .65 * DT)
        # I0's southbound discharge lands on the link; the link occupancy is
        # I0's downstream queue and I1's south approach queue.
        link_occ = len(link) + len(nodes["I1"]["queues"][1])
        packets = {}
        for name, node in nodes.items():
            down = node["down"][:]
            if name == "I0":
                down[1] = min(20., float(link_occ))
            packet = {"schema_version": 2, "sequence": step, "captured_at": 1e9 + t,
                      "counts": {a: min(100, len(node["queues"][i])) for i, a in enumerate(APPROACHES)},
                      "conflict_clear": True, "healthy": True,
                      "downstream_counts": dict(zip(APPROACHES, down)),
                      "downstream_capacity": dict.fromkeys(APPROACHES, 20),
                      "approaching": {a: sum(eta - t <= 4 for eta, _, _ in node["inbound"][i])
                                      for i, a in enumerate(APPROACHES)},
                      "arrival_rate": {a: len(node["recent"][i]) / 30 for i, a in enumerate(APPROACHES)},
                      "oldest_wait_s": {a: t - node["queues"][i][0][0] if node["queues"][i] else 0
                                        for i, a in enumerate(APPROACHES)}}
            packets[name] = packet
            node["last_obs"], node["received"] = Observation.parse(packet, 1e9 + t), t
        for name, node in nodes.items():
            intent = node["controller"].tick(t, node["last_obs"], node["received"])
            actual = node["cabinet"].accept(dict(intent, command_sequence=step, lease_s=.5), t)
            if (any(actual["lamps"][a] != "RED" for a in "NS")
                    and any(actual["lamps"][a] != "RED" for a in "EW")):
                raise RuntimeError("conflicting virtual cabinet outputs")
            if actual["fault"]:
                raise RuntimeError(f"unexpected virtual cabinet fault: {actual['fault']}")
            if actual["stage"] == "YELLOW" and last_stage[name] != "YELLOW":
                yellow_transitions += 1
            last_stage[name] = actual["stage"]
            last_lamps[name] = actual["lamps"]
            last_reason[name] = intent["reason"]
            for i, a in enumerate(APPROACHES):
                if actual["lamps"][a] != "RED" and actual["lamps"][a] != "GREEN":
                    node["next_depart"][i] = t + 1.0
                elif actual["lamps"][a] == "GREEN" and node["queues"][i] and node["down"][i] + 1 <= 20 and t >= node["next_depart"][i]:
                    stopline_t, spawn, vid = node["queues"][i].popleft()
                    if name == "I0" and i == 1:
                        # Northbound through movement: onto the link.
                        link.append((t + LINK_TRAVEL_S, t, spawn, vid))
                    else:
                        exited += 1
                        free_flow = APPROACH_TRAVEL_S + (LINK_TRAVEL_S if name == "I1" and i == 1 else 0)
                        wait = max(0, t - spawn - free_flow)
                        completed_waits.append(wait)
                        maximum_wait = max(maximum_wait, wait)
                    node["down"][i] += 1
                    node["next_depart"][i] = t + 2.0
        queued = sum(len(n["queues"][i]) for n in nodes.values() for i in range(4))
        if step < int(duration / DT):
            accrued_delay += queued * DT
        maximum_wait = max([maximum_wait] + [t - q[0][0] for n in nodes.values()
                                             for q in n["queues"] if q])
        if trace and step % 4 == 0:
            frames.append({"t": t,
                           "queues": {n: list(map(len, nodes[n]["queues"])) for n in nodes},
                           "link": len(link),
                           "lamps": {n: last_lamps[n] for n in nodes},
                           "reason": {n: last_reason[n] for n in nodes},
                           "arrived": arrived, "exited": exited,
                           "delay_s": round(accrued_delay, 2)})
    inbound = sum(len(n["inbound"][i]) for n in nodes.values() for i in range(4))
    remaining = queued + len(link) + inbound
    assert arrived == exited + remaining, "corridor vehicle conservation failed"
    waits = sorted(completed_waits)
    return {"scenario": "corridor", "seed": seed, "duration_s": duration, "controller": mode,
            "coordinated": coordinated, "arrival_sha256": fingerprint,
            "arrived": arrived, "exited": exited, "unfinished": remaining,
            "accrued_delay_s": round(accrued_delay, 3),
            "mean_delay_s": round(accrued_delay / max(arrived, 1), 3),
            "p95_completed_wait_s": round(waits[min(len(waits) - 1, int(.95 * len(waits)))], 3) if waits else None,
            "max_observed_wait_s": round(maximum_wait, 3), "changes": yellow_transitions,
            "coordinator": coordinator.snapshot() if coordinator else None,
            "frames": frames}


# ---------------------------------------------------------------------------
# N x M grid: a network of intersections connected by finite links.  Each
# node runs the same safety kernel and cabinet guard as the corridor; the
# Coordinator spans every link so supply hints, platoon-arrival boosts and
# route costs work across the whole network.  Vehicles enter at the grid
# boundary, traverse a random path of adjacent nodes and exit at the far
# boundary.  This is the network generalisation of simulate_corridor.

GRID_LINK_S = 12.0
GRID_APPROACH_S = 6.0
GRID_RATES = {
    # (approach index): vehicles/second injected at each boundary node
    0: .05,   # north approach
    1: .10,   # south approach (main corridor platoon)
    2: .07,   # east approach
    3: .07,   # west approach
}
GRID_NODE_RATES = {
    # interior nodes get lighter local demand
    0: .02, 1: .05, 2: .03, 3: .03,
}


def grid_topology(rows=2, cols=2):
    """Node names ``R{r}C{c}`` and directed links in row-major order."""
    if rows < 2 or cols < 2 or rows > 4 or cols > 4:
        raise ValueError("grid must be 2..4 rows and 2..4 columns")
    nodes = [f"R{r}C{c}" for r in range(rows) for c in range(cols)]
    links = []
    for r in range(rows):
        for c in range(cols):
            name = f"R{r}C{c}"
            if c + 1 < cols:
                links.append((name, f"R{r}C{c + 1}", GRID_LINK_S))
                links.append((f"R{r}C{c + 1}", name, GRID_LINK_S))
            if r + 1 < rows:
                links.append((name, f"R{r + 1}C{c}", GRID_LINK_S))
                links.append((f"R{r + 1}C{c}", name, GRID_LINK_S))
    return nodes, links


def grid_stream(seed, duration, rows=2, cols=2, demand_scale=1.0):
    """Poisson arrivals at boundary nodes; each vehicle picks a random
    boundary exit and follows a random adjacent path toward it."""
    rng = random.Random(seed)
    nodes, _ = grid_topology(rows, cols)
    boundary = [n for n in nodes
                if n[1] == "0" or n[1] == str(cols - 1) or n[3] == "0" or n[3] == str(rows - 1)]
    stream = []
    for step in range(int(duration / DT)):
        t = step * DT
        for name in boundary:
            for approach, rate in GRID_RATES.items():
                limit, product, count = math.exp(-rate * demand_scale * DT), 1.0, 0
                while product > limit:
                    product *= rng.random()
                    count += 1
                for _ in range(count - 1):
                    spawn = round(t + rng.random() * DT, 5)
                    exits = [n for n in boundary if n != name]
                    exit_node = rng.choice(exits)
                    stream.append((spawn, name, approach, exit_node))
        for name in nodes:
            if name in boundary:
                continue
            for approach, rate in GRID_NODE_RATES.items():
                limit, product, count = math.exp(-rate * demand_scale * DT), 1.0, 0
                while product > limit:
                    product *= rng.random()
                    count += 1
                for _ in range(count - 1):
                    spawn = round(t + rng.random() * DT, 5)
                    exit_node = rng.choice(boundary)
                    stream.append((spawn, name, approach, exit_node))
    return sorted(stream)


def _grid_path(start, exit_node, rows, cols, rng):
    """Random adjacent-node walk from start to exit_node (inclusive)."""
    r, c = int(start[1]), int(start[3])
    er, ec = int(exit_node[1]), int(exit_node[3])
    path = [start]
    while (r, c) != (er, ec):
        options = []
        if c < ec:
            options.append((r, c + 1))
        if c > ec:
            options.append((r, c - 1))
        if r < er:
            options.append((r + 1, c))
        if r > er:
            options.append((r - 1, c))
        r, c = rng.choice(options)
        path.append(f"R{r}C{c}")
    return path


def simulate_grid(seed=17, duration=360, rows=2, cols=2, mode="max_pressure",
                  coordinated=True, stream=None, trace=False, demand_scale=1.0):
    if duration < 30 or duration > 3600 or duration % DT:
            raise ValueError("duration must be 30..3600 seconds in quarter-second steps")
    number(demand_scale, "demand_scale", .5, 1.5)
    nodes, links = grid_topology(rows, cols)
    stream = grid_stream(seed, duration, rows, cols, demand_scale) if stream is None else stream
    fingerprint = hashlib.sha256(json.dumps(stream, separators=(",", ":")).encode()).hexdigest()
    timing = Timing()
    coordinator = Coordinator(offsets={n: 0.0 for n in nodes}, cycle_s=80.0,
                              links=links) if coordinated else None
    state = {}
    for name in nodes:
        state[name] = {
            "controller": Controller(timing, 0, mode=mode, coordinator=coordinator,
                                     intersection=name),
            "cabinet": Guard(timing, 0),
            "queues": [deque() for _ in APPROACHES],
            "inbound": [deque() for _ in APPROACHES],
            "recent": [deque() for _ in APPROACHES],
            "down": [0.] * 4,
            "next_depart": [0.] * 4,
            "last_obs": None, "received": None,
        }
    # link queues: (upstream, downstream) -> deque of (arrival_t, release_t, spawn, vid, path)
    link_q = {key: deque() for key in ((u, d) for u, d, _ in links)}
    arrived = exited = pos = 0
    accrued_delay = maximum_wait = 0.
    completed_waits = []
    last_stage = {n: "ALL_RED" for n in nodes}
    last_lamps = {n: dict.fromkeys(APPROACHES, "RED") for n in nodes}
    last_reason = {n: None for n in nodes}
    yellow_transitions = 0
    frames = []
    rng = random.Random(seed ^ 0x5EED)
    for step in range(int(duration / DT) + 1):
        t = step * DT
        while pos < len(stream) and stream[pos][0] <= t:
            spawn, name, approach, exit_node = stream[pos]
            arrived += 1
            path = _grid_path(name, exit_node, rows, cols, rng)
            state[name]["inbound"][approach].append(
                (spawn + GRID_APPROACH_S, spawn, arrived, path))
            pos += 1
        # Vehicles finish link travel and join the downstream node's queue.
        for (up, down), dq in link_q.items():
            while dq and dq[0][0] <= t:
                _, released, spawn, vid, path = dq.popleft()
                if coordinator is not None:
                    coordinator.note_arrival(up, down, released, t)
                idx = path.index(down) + 1 if down in path else -1
                approach = 1 if 0 <= idx < len(path) else 3
                state[down]["queues"][approach].append((t, spawn, vid, path))
        for name in nodes:
            node = state[name]
            for i in range(4):
                while node["inbound"][i] and node["inbound"][i][0][0] <= t:
                    node["queues"][i].append(node["inbound"][i].popleft())
                while node["recent"][i] and node["recent"][i][0] < t - 30:
                    node["recent"][i].popleft()
                node["down"][i] = max(0., node["down"][i] - .65 * DT)
        packets = {}
        for name in nodes:
            node = state[name]
            down = node["down"][:]
            # Downstream occupancy: link queue + receiving node's approach queue.
            for i, a in enumerate(APPROACHES):
                for (up, d), dq in link_q.items():
                    if up == name and ((i == 1 and a == "S") or (i == 3 and a == "W")):
                        down[i] = min(20., float(len(dq) + len(state[d]["queues"][i])))
            packet = {"schema_version": 2, "sequence": step, "captured_at": 1e9 + t,
                      "counts": {a: min(100, len(node["queues"][i])) for i, a in enumerate(APPROACHES)},
                      "conflict_clear": True, "healthy": True,
                      "downstream_counts": dict(zip(APPROACHES, down)),
                      "downstream_capacity": dict.fromkeys(APPROACHES, 20),
                      "approaching": {a: sum(eta - t <= 4 for eta, _, _, _ in node["inbound"][i])
                                      for i, a in enumerate(APPROACHES)},
                      "arrival_rate": {a: len(node["recent"][i]) / 30 for i, a in enumerate(APPROACHES)},
                      "oldest_wait_s": {a: t - node["queues"][i][0][0] if node["queues"][i] else 0
                                        for i, a in enumerate(APPROACHES)}}
            packets[name] = packet
            node["last_obs"], node["received"] = Observation.parse(packet, 1e9 + t), t
        for name in nodes:
            node = state[name]
            intent = node["controller"].tick(t, node["last_obs"], node["received"])
            actual = node["cabinet"].accept(dict(intent, command_sequence=step, lease_s=.5), t)
            if (any(actual["lamps"][a] != "RED" for a in "NS")
                    and any(actual["lamps"][a] != "RED" for a in "EW")):
                raise RuntimeError("conflicting virtual cabinet outputs")
            if actual["fault"]:
                raise RuntimeError(f"unexpected virtual cabinet fault: {actual['fault']}")
            if actual["stage"] == "YELLOW" and last_stage[name] != "YELLOW":
                yellow_transitions += 1
            last_stage[name] = actual["stage"]
            last_lamps[name] = actual["lamps"]
            last_reason[name] = intent["reason"]
            for i, a in enumerate(APPROACHES):
                if actual["lamps"][a] != "RED" and actual["lamps"][a] != "GREEN":
                    node["next_depart"][i] = t + 1.0
                elif actual["lamps"][a] == "GREEN" and node["queues"][i] and node["down"][i] + 1 <= 20 and t >= node["next_depart"][i]:
                    stopline_t, spawn, vid, path = node["queues"][i].popleft()
                    here = path.index(name) if name in path else len(path) - 1
                    if here + 1 < len(path):
                        nxt = path[here + 1]
                        link_q[(name, nxt)].append((t + GRID_LINK_S, t, spawn, vid, path))
                    else:
                        exited += 1
                        free_flow = GRID_APPROACH_S + GRID_LINK_S * (len(path) - 1)
                        wait = max(0, t - spawn - free_flow)
                        completed_waits.append(wait)
                        maximum_wait = max(maximum_wait, wait)
                    node["down"][i] += 1
                    node["next_depart"][i] = t + 2.0
        queued = sum(len(n["queues"][i]) for n in state.values() for i in range(4))
        if step < int(duration / DT):
            accrued_delay += queued * DT
        maximum_wait = max([maximum_wait] + [t - q[0][0] for n in state.values()
                                             for q in n["queues"] if q])
        if trace and step % 4 == 0:
            frames.append({"t": t,
                           "queues": {n: list(map(len, state[n]["queues"])) for n in nodes},
                           "links": {f"{u}:{d}": len(dq) for (u, d), dq in link_q.items()},
                           "lamps": {n: last_lamps[n] for n in nodes},
                           "reason": {n: last_reason[n] for n in nodes},
                           "arrived": arrived, "exited": exited,
                           "delay_s": round(accrued_delay, 2)})
    inbound = sum(len(n["inbound"][i]) for n in state.values() for i in range(4))
    in_links = sum(len(dq) for dq in link_q.values())
    remaining = queued + in_links + inbound
    assert arrived == exited + remaining, "grid vehicle conservation failed"
    waits = sorted(completed_waits)
    return {"scenario": "grid", "seed": seed, "duration_s": duration,
            "rows": rows, "cols": cols, "controller": mode,
            "coordinated": coordinated, "arrival_sha256": fingerprint,
            "arrived": arrived, "exited": exited, "unfinished": remaining,
            "accrued_delay_s": round(accrued_delay, 3),
            "mean_delay_s": round(accrued_delay / max(arrived, 1), 3),
            "p95_completed_wait_s": (waits[min(len(waits) - 1, int(.95 * len(waits)))] if waits else None),
            "max_observed_wait_s": round(maximum_wait, 3), "changes": yellow_transitions,
            "coordinator": coordinator.snapshot() if coordinator else None,
            "frames": frames}
