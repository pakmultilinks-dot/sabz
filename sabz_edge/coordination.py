"""Corridor coordination: offsets, green waves, and upstream supply hints.

A Coordinator is optional and per-corridor.  Each intersection keeps its own
safety kernel and local policy; the coordinator only supplies:

* ``offset``        -- fixed time offset of the intersection's cycle origin so
                       adjacent signals can be phased into a green wave.
* ``supply_hint``   -- a downstream link's current receiving capacity (0..1),
                       folded into the local pressure so a queue never pours
                       vehicles into a link that cannot receive them.

Nothing here may touch lamp states or timing: the safety kernel in core.py
still owns every transition.
"""
from collections import deque
from math import isfinite

PHASES = ("NS", "EW")
PHASE_INDEX = {"NS": (0, 1), "EW": (2, 3)}


def number(value, name, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not isfinite(value):
        raise ValueError(f"{name} must be finite and in [{low}, {high}]")
    return float(value)


class Coordinator:
    def __init__(self, offsets=None, cycle_s=80.0, links=None):
        number(cycle_s, "cycle_s", 40.0, 200.0)
        self.cycle_s = cycle_s
        self.offsets = dict(offsets or {})
        # Corridor topology: (upstream, downstream, link travel seconds).
        self.links = [(str(u), str(d), number(t, "link_travel_s", 1.0, 300.0))
                      for u, d, t in (links or [])]
        self._supply = {}
        self._releases = {}
        # Closed-loop offset tuning: the configured plan is the anchor, and
        # observed link travel may only bend it, never rewrite it.
        self._offset_base = dict(self.offsets)
        self._last_tune = {}
        # Observed link travel: (upstream, downstream) -> recent samples and
        # an EWMA smoothed estimate seeded from the configured travel time.
        self._link_cfg = {(u, d): t for u, d, t in self.links}
        self._samples = {}
        self._ewma = {}

    SAMPLES_MAX = 32
    EWMA_ALPHA = 0.25
    MAX_TRAVEL_S = 300.0
    OFFSET_STEP_S = 4.0        # max seconds a single tune may move an offset
    OFFSET_MAX_ADJUST_S = 40.0 # max seconds from the configured plan

    def offset(self, intersection):
        return float(self.offsets.get(intersection, 0.0))

    def _wrap_delta(self, delta):
        """``delta`` folded into [-cycle/2, cycle/2) -- the shortest way round."""
        return (delta + self.cycle_s / 2) % self.cycle_s - self.cycle_s / 2

    def tune_offsets(self, now, min_interval_s=10.0):
        """Closed-loop offset tuning (SCOOT-style): aim each node's offset at
        the observed travel time of its incoming link(s), modulo the cycle.

        Bounded three ways so field offsets can never run away: at most
        OFFSET_STEP_S per tune, at most OFFSET_MAX_ADJUST_S (capped at half a
        cycle) from the configured plan, and at most one tune per node per
        ``min_interval_s``.  Nodes with several incoming links aim at their
        circular mean.  Returns {node: new_offset} for nodes that moved.
        """
        number(now, "now", 0, 1e12)
        number(min_interval_s, "min_interval_s", 1.0, 3600.0)
        targets = {}
        for upstream, downstream, _cfg in self.links:
            if downstream in self.offsets:
                targets.setdefault(downstream, []).append(
                    self.link_cost(upstream, downstream) % self.cycle_s)
        adjusted = {}
        for node, goals in targets.items():
            last = self._last_tune.get(node)
            if last is not None and now - last < min_interval_s:
                continue
            self._last_tune[node] = now
            # Circular mean of the incoming-link targets.
            target = (goals[0] + sum(self._wrap_delta(g - goals[0]) for g in goals)
                      / len(goals)) % self.cycle_s
            base = self._offset_base.get(node, self.offsets[node])
            limit = min(self.OFFSET_MAX_ADJUST_S, self.cycle_s / 2)
            desired = base + max(-limit, min(limit, self._wrap_delta(target - base)))
            step = max(-self.OFFSET_STEP_S,
                       min(self.OFFSET_STEP_S, self._wrap_delta(desired - self.offsets[node])))
            new = (self.offsets[node] + step) % self.cycle_s
            if new != self.offsets[node]:
                self.offsets[node] = new
                adjusted[node] = new
        return adjusted

    def set_supply_hint(self, intersection, phase, capacity_fraction):
        if capacity_fraction is None:
            self._supply.pop((intersection, phase), None)
            return
        number(capacity_fraction, "capacity_fraction", 0.0, 1.0)
        self._supply[(intersection, phase)] = float(capacity_fraction)

    def supply_hint(self, intersection, phase):
        return self._supply.get((intersection, phase))

    def note_release(self, intersection, phase, now, size=0):
        """Record that ``phase`` turned green at ``intersection`` at ``now``.

        ``size`` is the queue discharged by that green -- the platoon that
        will travel the downstream link.
        """
        self._releases[(str(intersection), phase)] = (float(now), int(size))

    def note_arrival(self, upstream, downstream, released_at, arrived_at):
        """Record a release->arrival sample for a link; True if accepted.

        Implausible samples (negative or > MAX_TRAVEL_S, e.g. clock jumps
        or dropped packets) are ignored rather than poisoning the estimate.
        """
        key = (str(upstream), str(downstream))
        if key not in self._link_cfg:
            raise ValueError(f"unknown link {upstream}->{downstream}")
        released_at, arrived_at = float(released_at), float(arrived_at)
        if not (isfinite(released_at) and isfinite(arrived_at)):
            return False
        travel = arrived_at - released_at
        if travel < 0.0 or travel > self.MAX_TRAVEL_S:
            return False
        samples = self._samples.setdefault(key, deque(maxlen=self.SAMPLES_MAX))
        samples.append(travel)
        previous = self._ewma.get(key, self._link_cfg[key])
        self._ewma[key] = previous + self.EWMA_ALPHA * (travel - previous)
        return True

    def link_cost(self, upstream, downstream):
        """Estimated travel seconds on a link (observed EWMA, else configured)."""
        key = (str(upstream), str(downstream))
        if key not in self._link_cfg:
            raise ValueError(f"unknown link {upstream}->{downstream}")
        return self._ewma.get(key, self._link_cfg[key])

    def route_cost(self, path):
        """Total estimated travel seconds along a path of intersections."""
        nodes = [str(n) for n in path]
        if len(nodes) < 2:
            raise ValueError("route needs at least two intersections")
        return sum(self.link_cost(u, d) for u, d in zip(nodes, nodes[1:]))

    def predicted_arrivals(self, intersection, now):
        """Platoon vehicles expected at ``intersection`` at ``now`` per phase.

        A release upstream sends its queue down the link; it arrives
        ``travel`` seconds later and discharges over a few seconds.
        """
        arrivals = {}
        for upstream, downstream, travel in self.links:
            if downstream != intersection:
                continue
            for (origin, phase), (released, size) in self._releases.items():
                if origin != upstream or size <= 0:
                    continue
                arrival = released + travel
                discharge = size / 0.4 + 4.0
                if arrival - 2.0 <= now <= arrival + discharge:
                    arrivals[phase] = arrivals.get(phase, 0) + size
        return arrivals

    def preferred_phase(self, intersection, now):
        """The phase a platoon in flight toward ``intersection`` needs, or None.

        Driven by actual upstream green releases (not a fixed time window):
        a release on the link upstream means its platoon arrives
        ``travel`` seconds later, and the downstream signal should prefer
        that phase while the platoon is in flight.
        """
        arrivals = self.predicted_arrivals(intersection, now)
        if not arrivals:
            return None
        return max(arrivals, key=arrivals.get)

    def snapshot(self):
        return {"cycle_s": self.cycle_s,
                "offsets": dict(self.offsets),
                "offset_adjustments": {n: round(self._wrap_delta(
                    self.offsets[n] - self._offset_base.get(n, 0.0)), 3)
                    for n in self.offsets},
                "links": [list(link) for link in self.links],
                "releases": {f"{k[0]}:{k[1]}": v[0] for k, v in self._releases.items()},
                "supply_hints": {f"{k[0]}:{k[1]}": v for k, v in self._supply.items()},
                "link_costs": {f"{u}:{d}": {
                    "configured": t,
                    "observed": (round(self._ewma[(u, d)], 3)
                                 if (u, d) in self._ewma else None),
                    "samples": len(self._samples.get((u, d), ()))}
                    for u, d, t in self.links}}


def phase_capacity_fraction(observation, phase):
    """Receiving capacity left on a phase's downstream links, 0..1."""
    if observation is None:
        return None
    if not getattr(observation, "downstream_counts", ()):
        return None
    fractions = []
    for i in PHASE_INDEX[phase]:
        capacity = observation.downstream_capacity[i]
        if capacity <= 0:
            fractions.append(0.0)
        else:
            fractions.append(max(0.0, 1.0 - observation.downstream_counts[i] / capacity))
    return min(fractions)


def downstream_intersection(corridor, intersection, phase):
    """The intersection downstream of ``phase``'s green, or None."""
    node = corridor.get(intersection)
    if not node:
        return None
    return node.get(phase.lower())
