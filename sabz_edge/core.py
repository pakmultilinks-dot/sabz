"""Deterministic two-phase bench controller; no networking or model dependencies.

Scope: opposing through movements only. No turns, pedestrians or preemption.
All time arguments are monotonic seconds. Exactly one transition per tick:
late scheduling never compresses yellow or clearance.
"""
from dataclasses import dataclass
from math import isfinite
from .adaptive import AdaptivePolicy

APPROACHES = ("N", "S", "E", "W")
GROUPS = {"NS": ("N", "S"), "EW": ("E", "W")}


def number(value, name, low, high):
    if type(value) not in (int, float) or not low <= value <= high or not isfinite(value):
        raise ValueError(f"{name} must be finite and in [{low}, {high}]")
    return float(value)


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

    def __post_init__(self):
        if type(self.require_metric_protection) is not bool:
            raise ValueError("require_metric_protection must be a boolean")
        for name in ("min_green", "max_green", "yellow", "all_red", "stale_after", "max_tick_gap"):
            number(getattr(self, name), name, 0.1, 300)
        number(self.demand_margin, "demand_margin", 0, 100)
        if self.min_green > self.max_green:
            raise ValueError("min_green exceeds max_green")


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

    @classmethod
    def parse(cls, data, wall_now):
        required = {"schema_version", "sequence", "captured_at", "counts", "conflict_clear", "healthy"}
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] not in (1, 2, 3):
            raise ValueError("expected observation schema version 1, 2 or 3")
        version = data["schema_version"]
        extended = ("downstream_counts", "downstream_capacity", "approaching", "arrival_rate", "oldest_wait_s")
        metric = ("nearest_moving_distance_m", "max_approach_speed_mps", "distance_uncertainty_m")
        if version >= 2:
            required.update(extended)
        if version == 3:
            required.update(metric)
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
        values = tuple(number(counts[a], f"counts.{a}", 0, 500 if version == 3 else 100) for a in APPROACHES)
        if type(data["conflict_clear"]) is not bool or type(data["healthy"]) is not bool:
            raise ValueError("conflict_clear and healthy must be booleans")
        extras = []
        if version >= 2:
            for field, low, high in zip(extended, (0, 1, 0, 0, 0), ((500, 500, 500, 5, 3600) if version == 3 else (100, 100, 100, 5, 3600))):
                mapping = data[field]
                if not isinstance(mapping, dict) or set(mapping) != set(APPROACHES):
                    raise ValueError(f"{field} must contain exactly N, S, E, W")
                extras.append(tuple(number(mapping[a], field, low, high) for a in APPROACHES))
            if any(d > c for d, c in zip(extras[0], extras[1])):
                raise ValueError("downstream count exceeds configured capacity")
        if version == 3:
            for field, high in zip(metric, (500, 70, 20)):
                mapping = data[field]
                if not isinstance(mapping, dict) or set(mapping) != set(APPROACHES):
                    raise ValueError(f"{field} must contain exactly N, S, E, W")
                extras.append(tuple(None if field == metric[0] and mapping[a] is None else
                                    number(mapping[a], field, 0, high) for a in APPROACHES))
            for distance, speed in zip(extras[5], extras[6]):
                if (distance is None) != (speed == 0):
                    raise ValueError("no moving detection requires null distance and zero speed")
        return cls(seq, stamp, values, data["conflict_clear"], data["healthy"], version, *extras)


class Controller:
    def __init__(self, timing, now, mode="adaptive"):
        if mode not in ("adaptive", "actuated", "fixed"):
            raise ValueError("unknown control mode")
        self.mode = mode
        self.policy = AdaptivePolicy()
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

    def trip(self, reason):
        # A latched application fault cannot be cleared by camera traffic.
        if self.fault is None:
            self.fault = reason

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
        metric_valid = (sensor_usable and observation.schema_version == 3
                        and now-received_at <= .2)
        metric_missing = sensor_usable and self.timing.require_metric_protection and not metric_valid
        usable = sensor_usable and (not self.timing.require_metric_protection or metric_valid)
        extended = usable and observation.schema_version >= 2
        if extended:
            self.policy.inspect(observation, now)
            if self.stage == "GREEN":
                self.policy.mark_service_opportunity(self.phase, now)
        else:
            self.policy.details = {}
        self.active_policy = (self.policy.name if extended and self.mode == "adaptive" else
                              "actuated-v1" if usable and self.mode == "adaptive" else
                              self.mode if usable else "unavailable")
        self.approach_protection = "unavailable"
        protected = False
        if sensor_usable and observation.schema_version == 3:
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

        if self.stage == "GREEN":
            reason = None
            if not usable:
                reason = self.fault or ("metric_sensor_unavailable" if metric_missing else "sensor_unavailable")
            elif elapsed >= self.timing.max_green:
                reason = "maximum_green"
            elif self.mode == "fixed" and elapsed >= 25:
                reason = "fixed_plan"
            elif elapsed >= self.timing.min_green:
                if self.mode == "adaptive" and extended:
                    reason = self.policy.switch_reason(self.phase, other, now, elapsed)
                elif self.mode != "fixed":
                    counts = dict(zip(APPROACHES, observation.counts))
                    current = sum(counts[a] for a in GROUPS[self.phase])
                    waiting = sum(counts[a] for a in GROUPS[other])
                    if waiting > 0 and (current == 0 or waiting > current + self.timing.demand_margin):
                        reason = "opposing_demand"
            if reason and protected and reason not in ("maximum_green", "fixed_plan", "sensor_unavailable", "metric_sensor_unavailable") and not self.fault:
                reason = None
                self.reason = "approach_protection_70m"
            if reason:
                self.stage, self.entered, self.reason = "YELLOW", now, reason
            elif protected:
                self.reason = "approach_protection_70m"
            elif extended and self.mode == "adaptive":
                self.reason = "minimum_green" if elapsed < self.timing.min_green else "hold_current_demand"
        elif self.stage == "YELLOW":
            if elapsed >= self.timing.yellow:
                self.stage, self.entered = "ALL_RED", now
                self.phase = other
                self.reason = "clearance"
        elif self.stage == "ALL_RED":
            if extended and self.mode == "adaptive":
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
                if extended:
                    self.policy.mark_service_opportunity(self.phase, now)
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
        return {"schema_version": 1, "stage": self.stage, "phase": self.phase,
                "elapsed_s": max(0.0, now - self.entered), "lamps": lamps,
                "reason": self.reason, "fault": self.fault,
                "algorithm": self.active_policy,
                "approach_protection": self.approach_protection,
                "metric_protection_required": self.timing.require_metric_protection,
                "phase_scores": self.policy.details}
