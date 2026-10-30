"""Schema v5 emergency preemption: request semantics, fail-safe limits, auth."""
import json
import tempfile
import unittest
from pathlib import Path

from sabz_edge.cabinet_model import Guard
from sabz_edge.client import CameraClient
from sabz_edge.core import Controller, Observation, Timing
from sabz_edge.runtime import Runtime
from sabz_edge.store import Store

import test_edge as fixtures
from test_edge import Clock, HTTPTests, payload


def v5(seq=1, stamp=1000, emergency=None):
    data = payload(seq=seq, stamp=stamp)
    data.update({"schema_version": 5,
                 "downstream_counts": dict.fromkeys("NSEW", 0),
                 "downstream_capacity": dict.fromkeys("NSEW", 100),
                 "approaching": dict.fromkeys("NSEW", 0),
                 "arrival_rate": dict.fromkeys("NSEW", 0),
                 "oldest_wait_s": dict.fromkeys("NSEW", 0),
                 "nearest_moving_distance_m": dict.fromkeys("NSEW", None),
                 "max_approach_speed_mps": dict.fromkeys("NSEW", 0),
                 "distance_uncertainty_m": dict.fromkeys("NSEW", 0),
                 "pedestrian_queue": dict.fromkeys("NSEW", 0),
                 "emergency": emergency or dict.fromkeys("NSEW", 0)})
    return data


class ParseTests(unittest.TestCase):
    def test_v5_round_trip_and_v1_to_v4_backward_compatibility(self):
        obs = Observation.parse(v5(emergency={"N": 1, "S": 0, "E": 0, "W": 0}), 1000)
        self.assertEqual(obs.schema_version, 5)
        self.assertEqual(obs.emergency, (1.0, 0.0, 0.0, 0.0))
        for version in (1, 2, 3, 4):
            data = payload()
            if version >= 2:
                data.update({"schema_version": 2,
                             "downstream_counts": dict.fromkeys("NSEW", 0),
                             "downstream_capacity": dict.fromkeys("NSEW", 100),
                             "approaching": dict.fromkeys("NSEW", 0),
                             "arrival_rate": dict.fromkeys("NSEW", 0),
                             "oldest_wait_s": dict.fromkeys("NSEW", 0)})
            if version >= 3:
                data.update({"schema_version": 3,
                             "nearest_moving_distance_m": dict.fromkeys("NSEW", None),
                             "max_approach_speed_mps": dict.fromkeys("NSEW", 0),
                             "distance_uncertainty_m": dict.fromkeys("NSEW", 0)})
            if version >= 4:
                data.update({"schema_version": 4,
                             "pedestrian_queue": dict.fromkeys("NSEW", 0)})
            data["schema_version"] = version
            self.assertEqual(Observation.parse(data, 1000).schema_version, version)

    def test_v5_rejects_bad_emergency_flags(self):
        for emergency in ({"N": 0.5, "S": 0, "E": 0, "W": 0},
                          {"N": 1, "S": 1, "E": 0, "W": 0},
                          {"N": 1, "S": 0, "E": 0},
                          {"N": True, "S": 0, "E": 0, "W": 0}):
            with self.assertRaises(ValueError):
                Observation.parse(v5(emergency=emergency), 1000)
        missing = v5()
        del missing["emergency"]
        with self.assertRaises(ValueError):
            Observation.parse(missing, 1000)


class KernelTests(unittest.TestCase):
    def setUp(self):
        self.c = Controller(Timing(max_tick_gap=100), 0)

    def tick(self, now, **kw):
        obs = Observation.parse(payload(**kw), 1000)
        return self.c.tick(now, obs, now)

    def test_request_switches_phase_through_full_clearance(self):
        self.tick(1)
        self.tick(2)
        self.assertEqual(self.c.phase, "NS")
        self.c.request_preemption("E", 3)
        out = self.tick(3)
        self.assertEqual(out["stage"], "YELLOW")
        self.assertEqual(out["reason"], "emergency_preemption")
        self.assertEqual(out["lamps"], {"N": "YELLOW", "S": "YELLOW", "E": "RED", "W": "RED"})
        self.assertEqual(self.tick(6)["stage"], "ALL_RED")
        out = self.tick(9)
        self.assertEqual(out["stage"], "GREEN")
        self.assertEqual(out["lamps"], {"E": "GREEN", "W": "GREEN", "N": "RED", "S": "RED"})
        self.assertEqual(self.c.phase, "EW")

    def test_request_expires_after_sixty_seconds(self):
        self.tick(1)
        self.tick(2)
        self.c.request_preemption("E", 3)
        self.tick(3)
        self.tick(6)
        self.tick(9)
        self.assertIsNotNone(self.c.preempt_request)
        self.tick(63.01)
        self.assertIsNone(self.c.preempt_request)
        self.assertEqual(self.c.snapshot(63.01)["preemption"]["active"], False)

    def test_latched_fault_still_blocks_green(self):
        self.tick(1)
        self.tick(2)
        self.c.request_preemption("E", 3)
        self.c.trip("audit_or_adapter_failure")
        self.assertEqual(self.tick(3)["stage"], "YELLOW")
        self.assertEqual(self.tick(6)["stage"], "ALL_RED")
        out = self.tick(9)
        self.assertEqual(out["stage"], "ALL_RED")
        self.assertEqual(out["fault"], "audit_or_adapter_failure")

    def test_snapshot_reports_preemption_state(self):
        self.tick(1)
        self.tick(2)
        self.assertEqual(self.c.snapshot(2)["preemption"],
                         {"active": False, "approach": None, "reason": None})
        self.c.request_preemption("S", 3)
        snap = self.c.snapshot(3)
        self.assertEqual(snap["preemption"],
                         {"active": True, "approach": "S", "reason": "clearance_complete"})

    def test_invalid_approach_rejected(self):
        with self.assertRaises(ValueError):
            self.c.request_preemption("X", 1)


class RuntimeTests(unittest.TestCase):
    def test_preempt_records_event_and_rejects_unknown_approach(self):
        store = Store(":memory:")
        clock = Clock()
        runtime = Runtime(store, clock=clock, wall=lambda: 1000)
        try:
            runtime.preempt("E")
            row = store.db.execute(
                "SELECT kind, payload FROM events WHERE kind='preemption_requested'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(json.loads(row[1])["approach"], "E")
            with self.assertRaises(ValueError):
                runtime.preempt("X")
        finally:
            runtime.close()

    def test_status_embeds_preemption_key(self):
        store = Store(":memory:")
        clock = Clock()
        runtime = Runtime(store, clock=clock, wall=lambda: 1000)
        try:
            runtime.submit("camera", Observation.parse(payload(), 1000))
            clock.now = 1
            runtime.tick()
            self.assertIn("preemption", runtime.status()["controller"])
        finally:
            runtime.close()


class GuardTests(unittest.TestCase):
    def command(self, seq, stage, phase, reason=None, fault=False):
        lamps = dict.fromkeys("NSEW", "RED")
        if stage != "ALL_RED":
            for a in ("N", "S") if phase == "NS" else ("E", "W"):
                lamps[a] = stage
        command = {"command_sequence": seq, "lease_s": .5,
                   "stage": stage, "phase": phase, "lamps": lamps}
        if reason:
            command["reason"] = reason
        if fault:
            command["fault"] = True
        return command

    def test_preemption_reason_allows_early_transition_but_never_skips_yellow(self):
        fast = Timing(min_green=.1, max_green=.8, yellow=.2, all_red=.1)
        guard = Guard(fast, 0)
        guard.accept(self.command(1, "GREEN", "NS"), .1)
        self.assertEqual(guard.stage, "GREEN")
        # An emergency reason may end green early (elapsed < min_green)...
        out = guard.accept(self.command(2, "YELLOW", "NS", reason="emergency_preemption"), .15)
        self.assertEqual(out["stage"], "YELLOW")
        # ...but a GREEN command can never skip the yellow interval.
        out = guard.accept(self.command(3, "GREEN", "NS"), .15 + fast.yellow - .01)
        self.assertEqual(out["stage"], "YELLOW")
        # Once yellow elapses, advance() moves to ALL_RED and flips the phase.
        out = guard.accept(self.command(4, "GREEN", "NS"), .15 + fast.yellow + .01)
        self.assertEqual(out["stage"], "ALL_RED")
        self.assertEqual(out["phase"], "EW")
        # ALL_RED must also elapse before green resumes.
        out = guard.accept(self.command(5, "GREEN", "NS"),
                           .15 + fast.yellow + .01 + fast.all_red + .01)
        self.assertEqual(out["stage"], "GREEN")

    def test_unknown_reason_still_requires_min_green(self):
        fast = Timing(min_green=.1, max_green=.8, yellow=.2, all_red=.1)
        guard = Guard(fast, 0)
        guard.accept(self.command(1, "GREEN", "NS"), .1)
        out = guard.accept(self.command(2, "YELLOW", "NS", reason="some_other_reason"), .15)
        self.assertEqual(out["stage"], "GREEN")
        out = guard.accept(self.command(3, "YELLOW", "NS"), .1 + fast.min_green)
        self.assertEqual(out["stage"], "YELLOW")


class ServerTests(HTTPTests):
    def test_preemption_requires_reader_token_and_valid_body(self):
        camera, reader = "c" * 32, "r" * 32
        self.assertEqual(self.request("POST", "/v1/preemption", {"approach": "E"})[0], 401)
        self.assertEqual(self.request("POST", "/v1/preemption", {"approach": "E"},
                                      token=camera)[0], 401)
        code, body = self.request("POST", "/v1/preemption", {"approach": "E"}, token=reader)
        self.assertEqual(code, 202)
        self.assertEqual(body, {"accepted": True, "approach": "E", "mode": "bench"})
        for bad in ({"approach": "X"}, {"approach": "E", "extra": 1}, {}, []):
            self.assertEqual(self.request("POST", "/v1/preemption", bad, token=reader)[0], 400)
        self.assertEqual(self.request("POST", "/v1/observations", {"approach": "E"},
                                      token=reader)[0], 401)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.client = CameraClient("http://127.0.0.1:1", "c" * 32,
                                   str(Path(self.directory.name) / "sender.db"))

    def tearDown(self):
        self.client.close()
        self.directory.cleanup()

    def test_emergency_requires_v5_context(self):
        with self.assertRaises(ValueError):
            self.client.send(dict.fromkeys("NSEW", 0), emergency=dict.fromkeys("NSEW", 0))
        traffic = dict.fromkeys(("downstream_counts", "downstream_capacity",
                                 "approaching", "arrival_rate", "oldest_wait_s"),
                                dict.fromkeys("NSEW", 0))
        metrics = dict.fromkeys(("nearest_moving_distance_m", "max_approach_speed_mps",
                                 "distance_uncertainty_m"), dict.fromkeys("NSEW", 0))
        metrics["nearest_moving_distance_m"] = dict.fromkeys("NSEW", None)
        for emergency in ({"N": 0.5, "S": 0, "E": 0, "W": 0},
                          {"N": 1, "S": 1, "E": 0, "W": 0},
                          {"N": 1, "S": 0, "E": 0},
                          {"N": True, "S": 0, "E": 0, "W": 0}):
            with self.assertRaises(ValueError):
                self.client.send(dict.fromkeys("NSEW", 0), traffic_state=traffic,
                                 approach_state=metrics, emergency=emergency)


if __name__ == "__main__":
    unittest.main()