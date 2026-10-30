"""Single control owner, paced independently of incoming HTTP observations."""
import json
import threading
import time
import copy
from collections import deque

from .core import Controller, Observation, Timing


class BenchAdapter:
    """In-memory lamp emulator. Never opens GPIO, serial, PLC or network outputs."""
    name = "bench-emulator"

    def __init__(self):
        self.last = None

    def apply(self, command):
        lamps = command["lamps"]
        ns_active = any(lamps[a] != "RED" for a in "NS")
        ew_active = any(lamps[a] != "RED" for a in "EW")
        if ns_active and ew_active:
            raise RuntimeError("conflicting outputs")
        self.last = dict(command)


class Runtime:
    def __init__(self, store, timing=None, clock=time.monotonic, wall=time.time):
        self.store, self.clock, self.wall = store, clock, wall
        self.lock = threading.RLock()
        self.controller = Controller(timing or Timing(), clock())
        self.adapter = BenchAdapter()
        self.observation = None
        self.metrics = None
        self.telemetry_sequence = 0
        self.telemetry_source = "telemetry"
        self.received_at = None
        self.telemetry_received_at = None
        self.stop_event = threading.Event()
        self.thread = None
        self.last_error = None
        self.command_sequence = 0
        self.history = deque(maxlen=20)
        self.last_transition = None
        self.last_acknowledgement = None
        self.output = None
        self.last_completed_tick = None
        self.alert_log = None
        self._prev_fault = None
        self._prev_fresh = None

    def submit(self, source, observation):
        with self.lock:
            now = self.clock()
            # Preserve capture age: a delayed packet must not gain a new full TTL.
            age = max(0.0, self.wall() - observation.captured_at)
            if age > self.controller.timing.stale_after:
                raise ValueError("observation expired before acceptance")
            self.store.accept(source, observation)
            if self.clock() - now + age > self.controller.timing.stale_after:
                raise ValueError("observation expired during durable acceptance")
            self.observation, self.received_at = observation, now - age
            # Dashboard view of the accepted metric stream; aggregates only.
            self.metrics = {"sequence": observation.sequence,
                            "schema_version": observation.schema_version,
                            "captured_at": observation.captured_at,
                            "received_age_s": age,
                            "healthy": observation.healthy,
                            "conflict_clear": observation.conflict_clear,
                            "counts": dict(zip(("N", "S", "E", "W"), observation.counts)),
                            "approaching": dict(zip(("N", "S", "E", "W"), observation.approaching)),
                            "arrival_rate": dict(zip(("N", "S", "E", "W"), observation.arrival_rate)),
                            "oldest_wait_s": dict(zip(("N", "S", "E", "W"), observation.oldest_wait_s)),
                            "pedestrian_queue": dict(zip(("N", "S", "E", "W"), observation.pedestrian_queue)),
                                                        "emergency": dict(zip(("N", "S", "E", "W"), observation.emergency)),
                                                        "class_counts": dict(zip(("N", "S", "E", "W"), observation.class_counts))}

    def submit_telemetry(self, counts, conflict_clear, healthy):
        """Accept a counts-only dashboard feed (schema v1) without a metric stream."""
        with self.lock:
            now = self.clock()
            stamp = self.wall()
            observation = Observation.parse(
                {"schema_version": 1, "sequence": self.telemetry_sequence,
                 "captured_at": stamp, "counts": counts,
                 "conflict_clear": conflict_clear, "healthy": healthy}, stamp)
            self.telemetry_sequence += 1
            age = max(0.0, self.wall() - observation.captured_at)
            if age > self.controller.timing.stale_after:
                raise ValueError("observation expired before acceptance")
            self.store.accept(self.telemetry_source, observation)
            if self.clock() - now + age > self.controller.timing.stale_after:
                raise ValueError("observation expired during durable acceptance")
            # The counts-only feed is a dashboard view; it must never
            # replace the control observation/received_at pair that
            # tick() and status() consume as a unit.
            self.telemetry_received_at = now - age
            self.metrics = {"sequence": observation.sequence,
                            "schema_version": 1,
                            "captured_at": observation.captured_at,
                            "received_age_s": age,
                            "healthy": observation.healthy,
                            "conflict_clear": observation.conflict_clear,
                            "counts": dict(zip(("N", "S", "E", "W"), observation.counts)),
                            "approaching": {}, "arrival_rate": {}, "oldest_wait_s": {},
                                                        "pedestrian_queue": {}, "emergency": {}, "class_counts": {}}
            return observation.sequence

    def set_alert_log(self, path):
        """Mirror alert events to a local JSONL alert log (best effort)."""
        self.alert_log = path

    def _alert(self, kind, payload):
        """Journal a deduplicated alert event and mirror it to the local alert log."""
        record = {"kind": kind, **payload}
        self.store.event("alert", record)
        if self.alert_log:
            try:
                with open(self.alert_log, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, sort_keys=True) + "\n")
            except OSError:
                pass

    def preempt(self, approach):
        with self.lock:
            if approach not in ("N", "S", "E", "W"):
                raise ValueError("approach must be N, S, E or W")
            self.controller.request_preemption(approach, self.clock())
            self.store.event("preemption_requested", {"approach": approach})
            self._alert("preemption_requested", {"approach": approach})

    def tick(self):
        with self.lock:
            now = self.clock()
            candidate = copy.deepcopy(self.controller)
            snapshot = candidate.tick(now, self.observation, self.received_at)
            signature = (snapshot["stage"], snapshot["phase"], snapshot["reason"], snapshot["fault"])
            try:
                # Edge-triggered alerts: journaled once per state change, inside
                # the audit path so a journal failure latches the fault.
                fault = snapshot["fault"]
                if fault is not None and fault != self._prev_fault:
                    self._alert("fault_latched", {"fault": fault})
                self._prev_fault = fault
                age = (None if self.received_at is None
                       else max(0.0, now - self.received_at))
                fresh = age is not None and age <= self.controller.timing.stale_after
                if self._prev_fresh is not None and fresh != self._prev_fresh:
                    if fresh:
                        self._alert("sensor_recovered", {})
                    else:
                        self._alert("sensor_lost", {"age_s": age})
                self._prev_fresh = fresh
                if signature != self.last_transition:
                    self.store.event("transition_intent", snapshot)
                applied_at = self.clock()
                if applied_at - now > self.controller.timing.max_tick_gap:
                    raise RuntimeError("control cycle expired during audit")
                sensor_deadline = (.2 if self.controller.timing.require_metric_protection
                                   else self.controller.timing.stale_after)
                if snapshot["stage"] == "GREEN" and (self.received_at is None or
                        not 0 <= applied_at - self.received_at <= sensor_deadline):
                    raise RuntimeError("sensor expired during audit")
                if candidate.stage != self.controller.stage:
                    candidate.entered = applied_at
                candidate.last_tick = applied_at
                snapshot = candidate.snapshot(applied_at)
                self.command_sequence += 1
                command = dict(snapshot, command_sequence=self.command_sequence,
                               lease_s=0.5, adapter=self.adapter.name,
                               observation_sequence=(self.observation.sequence if self.observation else None))
                self.adapter.apply(command)
                self.controller = candidate
                self.output = command
                self.history.append(command)
                readback = getattr(self.adapter, "readback", None)
                actual = readback or snapshot
                ack = (actual["stage"], actual["phase"], actual.get("fault"))
                if signature != self.last_transition or ack != self.last_acknowledgement:
                    self.store.event("output_acknowledged", {"command_sequence": self.command_sequence,
                                      "requested": snapshot, "cabinet_readback": readback})
                self.last_transition = signature
                self.last_acknowledgement = ack
                self.last_completed_tick = self.clock()
            except Exception:
                self.last_error = "audit_or_adapter_failure"
                self.controller.trip(self.last_error)
                self._alert("audit_failure", {"error": self.last_error})
                # Do not emit a green command after an audit failure. The next
                # control tick starts normal yellow clearance from a green.
                raise
            return command

    def status(self):
        if not self.lock.acquire(timeout=.1):
            return {"mode": "bench", "field_ready": False, "ready": False,
                    "loop_healthy": False, "error": "control_lock_busy",
                    "last_output": self.output, "adapter": self.adapter.name}
        try:
            now = self.clock()
            age = None if self.received_at is None else max(0, now - self.received_at)
            loop_healthy = (self.last_completed_tick is not None
                            and 0 <= now - self.last_completed_tick <= self.controller.timing.max_tick_gap)
            ready = (loop_healthy and self.last_error is None and self.controller.fault is None
                     and age is not None and age <= self.controller.timing.stale_after
                     and self.observation.healthy
                     and (not self.controller.timing.require_metric_protection or
                          (self.observation.schema_version >= 3 and age <= .2)))
            cabinet = None
            if hasattr(self.adapter, "status"):
                try:
                    cabinet = self.adapter.status()
                except (OSError, RuntimeError):
                    ready = False
            if cabinet and cabinet["fault"]:
                ready = False
            return {"mode": "bench", "field_ready": False, "ready": ready,
                    "adapter": self.adapter.name, "sensor_age_s": age, "loop_healthy": loop_healthy,
                    "controller": self.controller.snapshot(now),
                    "last_output": self.output, "cabinet_readback": cabinet, "error": self.last_error}
        finally:
            self.lock.release()

    def metrics_snapshot(self):
        """Read-only dashboard view: latest metric stream plus recent transitions."""
        if not self.lock.acquire(timeout=.1):
            return {"error": "control_lock_busy"}
        try:
            now = self.clock()
            # Freshness follows the control metric stream when present,
            # otherwise the counts-only telemetry feed.
            ref = (self.received_at if self.received_at is not None
                   else self.telemetry_received_at)
            age = None if ref is None else max(0, now - ref)
            fresh = age is not None and age <= self.controller.timing.stale_after
            snapshot = self.controller.snapshot(now)
            events, alerts = [], []
            try:
                rows = self.store.db.execute(
                    "SELECT at, kind, payload FROM events WHERE kind = 'transition_intent'"
                    " ORDER BY at DESC, rowid DESC LIMIT 20").fetchall()
                events = [{"at": row[0], "kind": row[1], "payload": json.loads(row[2])}
                          for row in rows]
                rows = self.store.db.execute(
                    "SELECT at, kind, payload FROM events WHERE kind = 'alert'"
                    " ORDER BY at DESC, rowid DESC LIMIT 20").fetchall()
                alerts = [{"at": row[0], "kind": row[1], "payload": json.loads(row[2])}
                          for row in rows]
            except (OSError, ValueError):
                events, alerts = [], []
            return {"mode": "bench", "field_ready": False, "now": now,
                    "sensor_age_s": age, "sensor_fresh": fresh,
                    "loop_healthy": (self.last_completed_tick is not None
                                     and 0 <= now - self.last_completed_tick
                                     <= self.controller.timing.max_tick_gap),
                    "last_error": self.last_error,
                    "controller": snapshot,
                    "metrics": self.metrics,
                    "recent_transitions": events,
                    "recent_alerts": alerts}
        finally:
            self.lock.release()

    def _run(self):
        while not self.stop_event.is_set():
            cycle_started = self.clock()
            try:
                self.tick()
            except Exception:
                # Keep attempting clearance; never clear the latched fault.
                pass
            # Pace start-to-start; processing time must not add a full extra
            # sleep to every cycle. This remains a soft real-time host loop.
            self.stop_event.wait(max(0.0, 0.05 - (self.clock() - cycle_started)))

    def start(self):
        if self.thread is not None:
            raise RuntimeError("runtime already started")
        # Adapter startup is outside the timed control epoch.
        if self.output is None:
            self.controller = Controller(self.controller.timing, self.clock())
        self.tick()
        self.thread = threading.Thread(target=self._run, name="sabz-control", daemon=True)
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)
        if hasattr(self.adapter, "close"):
            self.adapter.close()
        # The emulator is removed from service, not an immediate road signal
        # command. A real adapter must handle disconnect with its local plan.
        self.store.close()
