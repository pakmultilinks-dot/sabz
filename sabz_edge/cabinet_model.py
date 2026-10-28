"""Pure deterministic model of the bench cabinet, usable in simulation and WASM."""
from .core import APPROACHES, GROUPS, number


class Guard:
    def __init__(self, timing, now):
        self.timing = timing
        self.stage, self.phase, self.entered = "ALL_RED", "NS", now
        self.deadline = None
        self.sequence = -1
        self.fault = None
        self.reason = "startup"

    def trip(self, reason, now):
        if self.fault is None:
            self.fault = reason
        if self.stage == "GREEN":
            self.stage, self.entered = "YELLOW", now
        self.reason = self.fault

    def advance(self, now):
        if self.deadline is not None and now >= self.deadline:
            self.trip("lease_expired", now)
        if self.stage == "YELLOW" and now - self.entered >= self.timing.yellow:
            self.stage, self.entered = "ALL_RED", now
            self.phase = "EW" if self.phase == "NS" else "NS"
        if self.stage == "GREEN" and now - self.entered >= self.timing.max_green:
            self.stage, self.entered, self.reason = "YELLOW", now, "local_maximum_green"

    def accept(self, command, now):
        self.advance(now)
        try:
            seq = command["command_sequence"]
            if type(seq) is not int or not self.sequence < seq < 2**63:
                raise ValueError("command replay")
            lease = number(command["lease_s"], "lease_s", .1, .5)
            stage, phase = command["stage"], command["phase"]
            if stage not in ("GREEN", "YELLOW", "ALL_RED") or phase not in GROUPS:
                raise ValueError("invalid phase")
            lamps = dict.fromkeys(APPROACHES, "RED")
            if stage != "ALL_RED":
                for a in GROUPS[phase]:
                    lamps[a] = stage
            if command["lamps"] != lamps:
                raise ValueError("conflicting or invalid lamps")
        except (KeyError, TypeError, ValueError):
            self.trip("invalid_command", now)
            return self.snapshot(now)
        self.sequence, self.deadline = seq, now + lease
        if self.fault:
            return self.snapshot(now)
        elapsed = now - self.entered
        if self.stage == "GREEN":
            if stage == "GREEN" and phase != self.phase:
                self.trip("illegal_phase_change", now)
            elif stage != "GREEN":
                # A fault request may terminate early, but never skips yellow.
                fault_request = bool(command.get("fault")) or command.get("reason") in ("sensor_unavailable", "metric_sensor_unavailable")
                if elapsed >= self.timing.min_green or fault_request:
                    self.stage, self.entered, self.reason = "YELLOW", now, "edge_transition"
        elif self.stage == "ALL_RED" and stage == "GREEN":
            if elapsed >= self.timing.all_red:
                self.phase = phase
                self.stage, self.entered, self.reason = "GREEN", now, "clearance_complete"
        return self.snapshot(now)

    def snapshot(self, now):
        lamps = dict.fromkeys(APPROACHES, "RED")
        if self.stage != "ALL_RED":
            for a in GROUPS[self.phase]:
                lamps[a] = self.stage
        return {"stage": self.stage, "phase": self.phase, "lamps": lamps,
                "elapsed_s": max(0, now - self.entered), "fault": self.fault,
                "reason": self.reason, "acknowledged_sequence": self.sequence,
                "physical_hardware": False}

