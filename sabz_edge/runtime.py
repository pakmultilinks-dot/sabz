"""Single control owner, paced independently of incoming HTTP observations."""
import threading
import time
import copy
from collections import deque

from .core import Controller, Timing


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
        self.received_at = None
        self.stop_event = threading.Event()
        self.thread = None
        self.last_error = None
        self.command_sequence = 0
        self.history = deque(maxlen=20)
        self.last_transition = None
        self.last_acknowledgement = None
        self.output = None
        self.last_completed_tick = None

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

    def tick(self):
        with self.lock:
            now = self.clock()
            candidate = copy.deepcopy(self.controller)
            snapshot = candidate.tick(now, self.observation, self.received_at)
            signature = (snapshot["stage"], snapshot["phase"], snapshot["reason"], snapshot["fault"])
            try:
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
                          (self.observation.schema_version == 3 and age <= .2)))
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
