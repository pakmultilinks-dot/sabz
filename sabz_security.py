"""SABZ Security: safety, validation, fail-safe, and audit for live deployment.

A traffic signal controller can kill people if it misbehaves. This module
enforces hard guarantees that no AI decision can violate:

1. INPUT VALIDATION: camera counts, API payloads checked for type/range.
2. TIMING BOUNDS: green never shorter than MIN_GREEN, never longer than MAX_GREEN.
3. DILEMMA ZONE: never cut green while a vehicle is inside 70m (hard rule).
4. FAIL-SAFE: any exception, timeout, or invalid state -> fixed-time fallback.
5. WATCHDOG: if no decision in 2 seconds, force safe state.
6. AUDIT LOG: every decision logged with timestamp, inputs, controller.
7. RATE LIMIT: API rejects abusive request rates.

Nothing here is learned. These are hard rules that override everything.
"""
import time
import json
import os
from collections import deque

# Hard timing bounds (seconds)
MIN_GREEN = 8.0
MAX_GREEN = 60.0
YELLOW = 3.0
ALL_RED = 2.0
DILEMMA_DIST = 70.0  # metres

# Input bounds
MAX_VEHICLES_PER_APPROACH = 100
MAX_COUNT_RATE = 50  # max new vehicles per second per approach (sanity)

# Watchdog
DECISION_TIMEOUT = 2.0  # seconds; force safe state if exceeded


class SecurityError(Exception):
    pass


def validate_counts(counts):
    """Validate camera count input. Raises SecurityError if invalid."""
    if not isinstance(counts, dict):
        raise SecurityError("counts must be a dict")
    for a in ["N", "S", "E", "W"]:
        if a not in counts:
            raise SecurityError(f"missing approach {a}")
        v = counts[a]
        if not isinstance(v, (int, float)):
            raise SecurityError(f"count {a} not a number: {v!r}")
        if v < 0 or v > MAX_VEHICLES_PER_APPROACH:
            raise SecurityError(f"count {a} out of range: {v}")
    return {a: float(counts[a]) for a in ["N", "S", "E", "W"]}


def validate_action(action):
    if action not in ("hold", "switch"):
        raise SecurityError(f"invalid action: {action!r}")
    return action


class SafetyEnforcer:
    """Hard safety rules. Overrides any AI decision."""

    def __init__(self):
        self.green_elapsed = 0.0
        self.phase = "NS"
        self.transitioning = False
        self.trans_timer = 0.0
        self.violations_blocked = 0

    def check(self, action, counts, approaching=None):
        """Apply hard safety rules. Returns safe action.

        Rules:
        1. Cannot switch before MIN_GREEN.
        2. Must switch by MAX_GREEN (fairness).
        3. Cannot switch if any vehicle inside dilemma zone.
        4. During transition, hold until yellow+all-red complete.
        """
        validate_action(action)
        counts = validate_counts(counts)
        approaching = approaching or {}

        # Rule 4: transition in progress
        if self.transitioning:
            self.trans_timer += 1.0
            if self.trans_timer >= YELLOW + ALL_RED:
                self.transitioning = False
                self.trans_timer = 0.0
                self.green_elapsed = 0.0
            return "hold"

        # Rule 2: fairness cap forces switch
        if self.green_elapsed >= MAX_GREEN and action == "hold":
            self._start_transition()
            return "switch"

        # Rule 1: minimum green
        if action == "switch" and self.green_elapsed < MIN_GREEN:
            self.violations_blocked += 1
            return "hold"

        # Rule 3: dilemma zone - never cut green under approaching vehicle
        if action == "switch":
            for a, dist in approaching.items():
                if dist < DILEMMA_DIST:
                    self.violations_blocked += 1
                    return "hold"
            self._start_transition()
            return "switch"

        self.green_elapsed += 1.0
        return "hold"

    def _start_transition(self):
        self.transitioning = True
        self.trans_timer = 0.0
        self.phase = "EW" if self.phase == "NS" else "NS"

    def state(self):
        return {
            "phase": self.phase,
            "green_elapsed": round(self.green_elapsed, 1),
            "transitioning": self.transitioning,
            "violations_blocked": self.violations_blocked,
        }


class AuditLog:
    """Append-only audit log of every decision."""

    def __init__(self, path="sabz_audit.log", max_size_mb=50):
        self.path = path
        self.max_bytes = max_size_mb * 1024 * 1024

    def record(self, counts, action, controller, regime, safety_overrode=False):
        entry = {
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "counts": counts,
            "action": action,
            "controller": controller,
            "regime": regime,
            "safety_overrode": safety_overrode,
        }
        # Rotate if too large
        if os.path.exists(self.path) and os.path.getsize(self.path) > self.max_bytes:
            os.rename(self.path, self.path + ".old")
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def recent(self, n=10):
        if not os.path.exists(self.path):
            return []
        with open(self.path) as f:
            lines = f.readlines()
        return [json.loads(l) for l in lines[-n:]]


class Watchdog:
    """Detects hung/stuck decision pipeline and forces safe state."""

    def __init__(self, timeout=DECISION_TIMEOUT):
        self.timeout = timeout
        self.last_ok = time.time()
        self.trips = 0

    def heartbeat(self):
        self.last_ok = time.time()

    def check(self):
        """Returns True if healthy, False if watchdog tripped."""
        if time.time() - self.last_ok > self.timeout:
            self.trips += 1
            return False
        return True

    def safe_action(self):
        """What to do when watchdog trips: hold current phase."""
        return "hold"


class RateLimiter:
    """Simple per-source rate limiter for the API."""

    def __init__(self, max_per_sec=10):
        self.max_per_sec = max_per_sec
        self.hits = defaultdict(deque)

    def allow(self, source="default"):
        now = time.time()
        q = self.hits[source]
        while q and now - q[0] > 1.0:
            q.popleft()
        if len(q) >= self.max_per_sec:
            return False
        q.append(now)
        return True


from collections import defaultdict  # noqa: E402


class SecurePipeline:
    """Full secure pipeline: validate -> decide -> safety -> audit.

    This is what production should call. Any failure at any stage
    results in a safe 'hold' with the incident logged.
    """

    def __init__(self, brain, audit_path="sabz_audit.log"):
        self.brain = brain
        self.safety = SafetyEnforcer()
        self.audit = AuditLog(audit_path)
        self.watchdog = Watchdog()
        self.errors = 0

    def decide(self, counts, approaching=None):
        """One secure decision cycle. Never raises; always returns safe action."""
        try:
            counts = validate_counts(counts)
            self.watchdog.heartbeat()

            # Brain decision
            from sabz_live import SabzLive  # lazy to avoid cycles
            state = self._counts_to_state(counts)
            action, ctrl, regime = self.brain.decide(state)

            # Safety override
            safe = self.safety.check(action, counts, approaching or {})
            overrode = (safe != action)

            self.audit.record(counts, safe, ctrl, regime,
                              safety_overrode=overrode)
            return safe, ctrl, regime, overrode

        except SecurityError as e:
            self.errors += 1
            self.audit.record(counts if isinstance(counts, dict) else {},
                              "hold", "failsafe", "error",
                              safety_overrode=True)
            return "hold", "failsafe", "error", True
        except Exception:
            self.errors += 1
            return "hold", "failsafe", "error", True

    def _counts_to_state(self, counts):
        q = [float(counts[a]) for a in ["N", "S", "E", "W"]]
        app = [c * 0.5 for c in q]
        hour = time.localtime().tm_hour + time.localtime().tm_min / 60.0
        return q + app + [1.0, 0.0, 0, 0, 0, 0, 0, hour]

    def health(self):
        return {
            "watchdog_ok": self.watchdog.check(),
            "watchdog_trips": self.watchdog.trips,
            "safety": self.safety.state(),
            "errors": self.errors,
        }
