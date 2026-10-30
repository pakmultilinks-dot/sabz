"""Deterministic two-phase bench controller; no networking or model dependencies.

Scope: opposing through movements only. No turns; pedestrian demand enters
as a queue count (schema v4). Emergency preemption (schema v5) is an
explicitly requested corridor clearance, never an automatic detection.
Stopped-vehicle class breakdown per approach enters as class_counts
(schema v6); persons are counted as pedestrians, never as vehicles.
All time arguments are monotonic seconds. Exactly one transition per tick:
late scheduling never compresses yellow or clearance.
"""
from dataclasses import dataclass, field
from math import isfinite
from .adaptive import AdaptivePolicy, MaxPressurePolicy
from .coordination import phase_capacity_fraction

APPROACHES = ("N", "S", "E", "W")
GROUPS = {"NS": ("N", "S"), "EW": ("E", "W")}
VEHICLE_CLASSES = ("car", "motorcycle", "bicycle", "bus", "truck")


def number(value, name, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not isfinite(value):
        raise ValueError(f"{name} must be finite and in [{low}, {high}]")
    return float(value)


def whole_number(value, name):
    result = number(value, name, 0, 500)
    if result != int(result):
        raise ValueError(f"{name} must be a whole number")
    return result


@dataclass(frozen=True)
class Timing:
    min_green: float = 8.0
    max_green: float = 60.0
    yellow: float = 3.0
    all_red: float = 2.0
    stale_after: float = 3.0
    max_tick_gap: float = 1.0
    demand_margin: float = 2.0
    require_metric_protection: bool = False
    walk_min: float = 7.0
    walk_max: float = 20.0
    tsp_extension_s: float = 15.0
    accessibility: dict = field(default_factory=dict)

    def __post_init__(self):
        if type(self.require_metric_protection) is not bool:
            raise ValueError("require_metric_protection must be a boolean")
        for name in ("min_green", "max_green", "yellow", "all_red", "stale_after", "max_tick_gap",
                     "walk_min", "walk_max"):
            number(getattr(self, name), name, 0.1, 300)
        number(self.demand_margin, "demand_margin", 0, 100)
        if self.min_green > self.max_green:
            raise ValueError("min_green exceeds max_green")
        number(self.tsp_extension_s, "tsp_extension_s", 0.0, 120.0)
        if self.walk_min > self.walk_max:
            raise ValueError("walk_min exceeds walk_max")
        if not isinstance(self.accessibility, dict):
            raise ValueError("accessibility must be a mapping of approach to multiplier")
        for approach, factor in self.accessibility.items():
            if approach not in APPROACHES:
                raise ValueError(f"unknown accessibility approach {approach!r}")
            number(factor, f"accessibility[{approach}]", 1.0, 3.0)


@dataclass(frozen=True)
class Observation:
    sequence: int
    captured_at: float
    counts: tuple
    conflict_clear: bool
    healthy: bool
    schema_version: int = 1
    downstream_counts: tuple = ()
    downstream_capacity: tuple = ()
    approaching: tuple = ()
    arrival_rate: tuple = ()
    oldest_wait_s: tuple = ()
    nearest_moving_distance_m: tuple = ()
    max_approach_speed_mps: tuple = ()
    distance_uncertainty_m: tuple = ()
    pedestrian_queue: tuple = ()
    emergency: tuple = ()
    class_counts: tuple = ()

    @classmethod
    def parse(cls, data, wall_now):
        required = {"schema_version", "sequence", "captured_at", "counts", "conflict_clear", "healthy"}
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] not in (1, 2, 3, 4, 5, 6):
            raise ValueError("expected observation schema version 1, 2, 3, 4, 5 or 6")
        version = data["schema_version"]
        extended = ("downstream_counts", "downstream_capacity", "approaching", "arrival_rate", "oldest_wait_s")
        metric = ("nearest_moving_distance_m", "max_approach_speed_mps", "distance_uncertainty_m")
        if version >= 2:
            required.update(extended)
        if version >= 3:
            required.update(metric)
        if version >= 4:
            required.add("pedestrian_queue")
        if version >= 5:
            required.add("emergency")
        if version >= 6:
            required.add("class_counts")
        if set(data) != required:
            raise ValueError("observation fields do not match schema")
        seq = data["sequence"]
        if type(seq) is not int or not 0 <= seq < 2**63:
            raise ValueError("sequence must be a non-negative signed 64-bit integer")
        stamp = number(data["captured_at"], "captured_at", 0, 1e12)
        if not -1 <= wall_now - stamp <= 3:
            raise ValueError("observation is stale or future-dated")
        counts = data["counts"]
        if not isinstance(counts, dict) or set(counts) != set(APPROACHES):
            raise ValueError("counts must contain exactly N, S, E, W")
        values = tuple(number(counts[a], f"counts.{a}", 0, 500 if version >= 3 else 100) for a in APPROACHES)
        if type(data["conflict_clear"]) is not bool or type(data["healthy"]) is not bool:
            raise ValueError("conflict_clear and healthy must be booleans")
        extras = []
        if version >= 2:
            for field, low, high in zip(extended, (0, 1, 0, 0, 0), ((500, 500, 500, 5, 3600) if version >= 3 else (100, 100, 100, 5, 3600))):
                mapping = data[field]
                if not isinstance(mapping, dict) or set(mapping) != set(APPROACHES):
                    raise ValueError(f"{field} must contain exactly N, S, E, W")
                extras.append(tuple(number(mapping[a], field, low, high) for a in APPROACHES))
            if any(d > c for d, c in zip(extras[0], extras[1])):
                raise ValueError("downstream count exceeds configured capacity")
        if version >= 3:
            for field, high in zip(metric, (500, 70, 20)):
                mapping = data[field]
                if not isinstance(mapping, dict) or set(mapping) != set(APPROACHES):
                    raise ValueError(f"{field} must contain exactly N, S, E, W")
                extras.append(tuple(None if field == metric[0] and mapping[a] is None else
                                    number(mapping[a], field, 0, high) for a in APPROACHES))
            for distance, speed in zip(extras[5], extras[6]):
                if (distance is None) != (speed == 0):
                    raise ValueError("no moving detection requires null distance and zero speed")
        pedestrian_queue = ()
        if version >= 4:
            queue = data["pedestrian_queue"]
            if not isinstance(queue, dict) or set(queue) != set(APPROACHES):
                raise ValueError("pedestrian_queue must contain exactly N, S, E, W")
            pedestrian_queue = tuple(number(queue[a], "pedestrian_queue", 0, 500) for a in APPROACHES)
        emergency = ()
        if version >= 5:
            flag = data["emergency"]
            if not isinstance(flag, dict) or set(flag) != set(APPROACHES):
                raise ValueError("emergency must contain exactly N, S, E, W")
            emergency = tuple(number(flag[a], "emergency", 0, 1) for a in APPROACHES)
            if any(value not in (0.0, 1.0) for value in emergency):
                raise ValueError("emergency values must be 0 or 1")
            if emergency.count(1.0) > 1:
                raise ValueError("emergency may flag at most one approach")
        class_counts = ()
        if version >= 6:
            breakdown = data["class_counts"]
            if not isinstance(breakdown, dict) or set(breakdown) != set(APPROACHES):
                raise ValueError("class_counts must contain exactly N, S, E, W")
            per_approach = []
            for a in APPROACHES:
                classes = breakdown[a]
                if not isinstance(classes, dict) or set(classes) != set(VEHICLE_CLASSES):
                    raise ValueError(f"class_counts.{a} must contain exactly {', '.join(VEHICLE_CLASSES)}")
                per_approach.append({cls: whole_number(classes[cls], f"class_counts.{a}.{cls}")
                                     for cls in VEHICLE_CLASSES})
            class_counts = tuple(per_approach)
        return cls(seq, stamp, values, data["conflict_clear"], data["healthy"], version, *extras,
                   pedestrian_queue, emergency, class_counts)


class Controller:
    def __init__(self, timing, now, mode="adaptive", coordinator=None, intersection=None):
        if mode not in ("adaptive", "actuated", "fixed", "max_pressure"):
            raise ValueError("unknown control mode")
        self.mode = mode
        self.policy = MaxPressurePolicy() if mode == "max_pressure" else AdaptivePolicy()
        self.coordinator = coordinator
        self.intersection = intersection
        self.active_policy = "unavailable"
        self.timing = timing
        self.stage = "ALL_RED"
        self.phase = "NS"
        self.entered = now
        self.last_tick = now
        self.reason = "startup_clearance"
        self.fault = None
        self.last_served_phase = None
        self.approach_protection = "unavailable"
        self.tsp_hold_until = 0.0
        self.preempt_request = None
        self.walk_until = None
        self.accessibility = dict(timing.accessibility)

    def trip(self, reason):
        # A latched application fault cannot be cleared by camera traffic.
        if self.fault is None:
            self.fault = reason

    def _tsp_bus_waiting(self, observation):
        """True when a bus is queued on an approach served by the current phase."""
        counts = getattr(observation, "class_counts", ())
        if not counts:
            return False
        for i, approach in enumerate(APPROACHES):
            if approach in GROUPS[self.phase] and counts[i].get("bus", 0) > 0:
                return True
        return False

    def accessibility_factor(self, phase):
        # Site-configured accessibility (hospital/school/senior crossings)
        # lengthens service on the flagged approaches; unflagged sites are 1.0.
        return max((self.accessibility.get(a, 1.0) for a in GROUPS[phase]),
                   default=1.0)

    def request_preemption(self, approach, now):
        # An explicit, authenticated corridor-clearance request. It expires on
        # its own so a lost release can never latch the intersection forever.
        if approach not in APPROACHES:
            raise ValueError("approach must be N, S, E or W")
        self.preempt_request = (approach, now)

    def tick(self, now, observation=None, received_at=None):
        if now < self.last_tick:
            self.trip("clock_regression")
        elif now - self.last_tick > self.timing.max_tick_gap:
            self.trip("control_loop_overrun")
        self.last_tick = now
        elapsed = now - self.entered
        fresh = (observation is not None and received_at is not None
                 and 0 <= now - received_at <= self.timing.stale_after)
        sensor_usable = fresh and observation.healthy and not self.fault
        metric_valid = (sensor_usable and observation.schema_version >= 3
                        and now-received_at <= .2)
        metric_missing = sensor_usable and self.timing.require_metric_protection and not metric_valid
        usable = sensor_usable and (not self.timing.require_metric_protection or metric_valid)
        extended = usable and observation.schema_version >= 2
        if extended:
            if self.coordinator is not None and self.intersection is not None:
                # Corridor hint: how much receiving capacity the downstream
                # intersection currently offers, folded into local pressure.
                hints = {}
                for phase in ("NS", "EW"):
                    frac = phase_capacity_fraction(observation, phase)
                    self.coordinator.set_supply_hint(self.intersection, phase, frac)
                    hints[phase] = frac
                if hasattr(self.policy, "supply_hints"):
                    self.policy.supply_hints = hints
                if hasattr(self.policy, "platoon_arrivals"):
                    self.policy.platoon_arrivals = (
                        self.coordinator.predicted_arrivals(self.intersection, now))
            self.policy.inspect(observation, now)
            if self.stage == "GREEN":
                self.policy.mark_service_opportunity(self.phase, now)
        else:
            self.policy.details = {}
        self.active_policy = (self.policy.name if extended and self.mode in ("adaptive", "max_pressure") else
                              "actuated-v1" if usable and self.mode == "adaptive" else
                              self.mode if usable else "unavailable")
        self.approach_protection = "unavailable"
        protected = False
        if sensor_usable and observation.schema_version >= 3:
            age = now - received_at
            self.approach_protection = "expired" if age > .2 else "clear"
            if age <= .2:
                for i, approach in enumerate(APPROACHES):
                    if approach not in GROUPS[self.phase]:
                        continue
                    distance = observation.nearest_moving_distance_m[i]
                    speed = observation.max_approach_speed_mps[i]
                    if distance is not None and speed > .5:
                        lower_distance = max(0, distance - observation.distance_uncertainty_m[i] - speed * age)
                        if lower_distance <= 70 and lower_distance / speed <= 6:
                            protected = True
                if protected:
                    self.approach_protection = "bounded_hold"
        other = "EW" if self.phase == "NS" else "NS"
        preempt = None
        if self.preempt_request is not None:
            requested, requested_at = self.preempt_request
            if now - requested_at > 60:
                self.preempt_request = None
            else:
                preempt = "NS" if requested in GROUPS["NS"] else "EW"

        if self.stage == "GREEN":
            reason = None
            tsp_hold = False
            factor = self.accessibility_factor(self.phase)
            if preempt is not None and usable and self.phase != preempt:
                # Corridor clearance outranks demand and protection, never safety.
                reason = "emergency_preemption"
            elif not usable:
                reason = self.fault or ("metric_sensor_unavailable" if metric_missing else "sensor_unavailable")
            elif elapsed >= self.timing.max_green * factor:
                reason = "maximum_green"
            elif self.mode == "fixed" and elapsed >= 25 * factor:
                reason = "fixed_plan"
            elif self.walk_until is not None and now < self.walk_until:
                # Pedestrian walk holds the parallel green for at least walk_min;
                # only the safety-class exits above may end it, never a demand
                # switch. Persistent demand extends the walk, capped at walk_max.
                if extended and elapsed < self.timing.walk_max * factor:
                    if (len(observation.pedestrian_queue) == len(APPROACHES)
                            and any(observation.pedestrian_queue[i] > 0
                                    for i, approach in enumerate(APPROACHES)
                                    if approach in GROUPS[self.phase])):
                        self.walk_until = min(now + self.timing.walk_min * factor,
                                              self.entered + self.timing.walk_max * factor)
                reason = None
            elif elapsed >= self.timing.min_green * factor:
                if self._tsp_bus_waiting(observation):
                    # Transit signal priority: hold green for a queued bus,
                    # bounded by max_green (the maximum_green exit above wins).
                    self.tsp_hold_until = now + self.timing.tsp_extension_s
                    tsp_hold = True
                elif now < self.tsp_hold_until:
                    tsp_hold = True
                elif self.mode in ("adaptive", "max_pressure") and extended:
                    preferred = (self.coordinator.preferred_phase(self.intersection, now)
                                if self.coordinator is not None and self.intersection is not None else None)
                    reason = self.policy.switch_reason(self.phase, other, now, elapsed, preferred=preferred)
                elif self.mode != "fixed":
                    counts = dict(zip(APPROACHES, observation.counts))
                    current = sum(counts[a] for a in GROUPS[self.phase])
                    waiting = sum(counts[a] for a in GROUPS[other])
                    if waiting > 0 and (current == 0 or waiting > current + self.timing.demand_margin):
                        reason = "opposing_demand"
            if reason and protected and reason not in ("maximum_green", "fixed_plan", "sensor_unavailable", "metric_sensor_unavailable", "emergency_preemption") and not self.fault:
                reason = None
                self.reason = "approach_protection_70m"
            if reason:
                self.stage, self.entered, self.reason = "YELLOW", now, reason
            elif protected:
                self.reason = "approach_protection_70m"
            elif self.walk_until is not None and now < self.walk_until:
                self.reason = "pedestrian_walk"
            elif tsp_hold:
                self.reason = "tsp_extended"
            elif extended and self.mode in ("adaptive", "max_pressure"):
                self.reason = ("minimum_green" if elapsed < self.timing.min_green * factor
                               else "hold_current_demand")
        elif self.stage == "YELLOW":
            if elapsed >= self.timing.yellow:
                self.stage, self.entered = "ALL_RED", now
                self.phase = other
                self.reason = "clearance"
        elif self.stage == "ALL_RED":
            if preempt is not None:
                # Clearance selects its own phase; adaptive yield is suspended.
                self.phase = preempt
            elif extended and self.mode in ("adaptive", "max_pressure"):
                pending = self.policy.details[self.phase]
                # Once a phase has been served, actual eligible cross-demand gets
                # the next turn. Pressure may allocate duration, not steal turns.
                selected = (self.phase if self.last_served_phase is not None
                            and self.phase != self.last_served_phase
                            and pending["supply_available"] and pending["present"] > 0
                            else self.policy.next_phase(self.phase))
                if selected is None:
                    self.reason = "downstream_blocked"
                    return self.snapshot(now)
                self.phase = selected
            if elapsed >= self.timing.all_red and usable and observation.conflict_clear:
                self.stage, self.entered = "GREEN", now
                self.last_served_phase = self.phase
                self.tsp_hold_until = 0.0
                self.walk_until = None
                if extended:
                    self.policy.mark_service_opportunity(self.phase, now)
                    if self.coordinator is not None and self.intersection is not None:
                        counts = dict(zip(APPROACHES, observation.counts))
                        size = sum(counts[a] for a in GROUPS[self.phase])
                        self.coordinator.note_release(self.intersection, self.phase, now, size)
                    if (len(observation.pedestrian_queue) == len(APPROACHES)
                            and any(observation.pedestrian_queue[i] > 0
                                    for i, approach in enumerate(APPROACHES)
                                    if approach in GROUPS[self.phase])):
                        # Walk accompanies the parallel vehicle green and holds
                        # it for at least walk_min; demand may extend to walk_max.
                        # Accessibility crossings get a proportionally longer walk.
                        self.walk_until = (now + self.timing.walk_min
                                           * self.accessibility_factor(self.phase))
                self.reason = "clearance_complete"
            elif not usable:
                self.reason = self.fault or ("metric_sensor_unavailable" if metric_missing else "sensor_unavailable")
            elif not observation.conflict_clear:
                self.reason = "intersection_not_clear"
        else:
            raise RuntimeError("unknown controller stage")
        return self.snapshot(now)

    def snapshot(self, now):
        lamps = dict.fromkeys(APPROACHES, "RED")
        if self.stage in ("GREEN", "YELLOW"):
            for approach in GROUPS[self.phase]:
                lamps[approach] = self.stage
        preempted = self.preempt_request is not None
        walk_active = (self.stage == "GREEN" and self.walk_until is not None
                       and now < self.walk_until)
        return {"schema_version": 1, "stage": self.stage, "phase": self.phase,
        "elapsed_s": max(0.0, now - self.entered), "lamps": lamps,
        "reason": self.reason, "fault": self.fault,
        "algorithm": self.active_policy,
        "walk_active": walk_active,
        "accessibility": dict(self.accessibility),
        "approach_protection": self.approach_protection,
        "tsp_hold_until": self.tsp_hold_until,
                "metric_protection_required": self.timing.require_metric_protection,
                "phase_scores": self.policy.details,
                "preemption": {"active": preempted,
                               "approach": self.preempt_request[0] if preempted else None,
                               "reason": self.reason if preempted else None}}
