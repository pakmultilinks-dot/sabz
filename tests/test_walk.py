"""Pedestrian walk phase: scheduling, hold semantics, extension, safety exits."""
import json
import tempfile
import unittest
from pathlib import Path

from sabz_edge.core import Controller, Observation, Timing
from sabz_edge.runtime import Runtime
from sabz_edge.store import Store

from test_edge import payload


def v5(seq=1, stamp=1000, clear=True, healthy=True, counts=None, ped=None):
    data = payload(seq=seq, stamp=stamp, clear=clear, healthy=healthy, counts=counts)
    data.update({"schema_version": 5,
                 "downstream_counts": dict.fromkeys("NSEW", 0),
                 "downstream_capacity": dict.fromkeys("NSEW", 100),
                 "approaching": dict.fromkeys("NSEW", 0),
                 "arrival_rate": dict.fromkeys("NSEW", 0),
                 "oldest_wait_s": dict.fromkeys("NSEW", 0),
                 "nearest_moving_distance_m": dict.fromkeys("NSEW", None),
                 "max_approach_speed_mps": dict.fromkeys("NSEW", 0),
                 "distance_uncertainty_m": dict.fromkeys("NSEW", 0),
                 "pedestrian_queue": ped or dict.fromkeys("NSEW", 0),
                 "emergency": dict.fromkeys("NSEW", 0)})
    return data


def v3(seq=1, stamp=1000, clear=True, healthy=True, counts=None):
    data = payload(seq=seq, stamp=stamp, clear=clear, healthy=healthy, counts=counts)
    data.update({"schema_version": 3,
                 "downstream_counts": dict.fromkeys("NSEW", 0),
                 "downstream_capacity": dict.fromkeys("NSEW", 100),
                 "approaching": dict.fromkeys("NSEW", 0),
                 "arrival_rate": dict.fromkeys("NSEW", 0),
                 "oldest_wait_s": dict.fromkeys("NSEW", 0),
                 "nearest_moving_distance_m": dict.fromkeys("NSEW", None),
                 "max_approach_speed_mps": dict.fromkeys("NSEW", 0),
                 "distance_uncertainty_m": dict.fromkeys("NSEW", 0)})
    return data


class WalkKernelTests(unittest.TestCase):
    def setUp(self):
        self.c = Controller(Timing(max_tick_gap=100), 0)

    def tick(self, now, **kw):
        builder = kw.pop("builder", v5)
        obs = Observation.parse(builder(**kw), 1000)
        return self.c.tick(now, obs, now)

    def test_walk_served_on_ped_demand_at_green_entry(self):
        self.tick(1)
        out = self.tick(2, ped={"N": 3, "S": 0, "E": 0, "W": 0})
        self.assertEqual(out["stage"], "GREEN")
        self.assertTrue(out["walk_active"])
        self.assertEqual(out["lamps"], {"N": "GREEN", "S": "GREEN", "E": "RED", "W": "RED"})
        # The next tick inside the walk window reports the walk reason.
        out = self.tick(3, ped={"N": 3, "S": 0, "E": 0, "W": 0})
        self.assertEqual(out["reason"], "pedestrian_walk")
        self.assertTrue(out["walk_active"])

    def test_no_walk_without_ped_demand(self):
        self.tick(1)
        out = self.tick(2)
        self.assertEqual(out["stage"], "GREEN")
        self.assertFalse(out["walk_active"])
        self.assertNotEqual(out["reason"], "pedestrian_walk")

    def test_walk_demand_on_opposing_group_does_not_trigger_walk(self):
        # Vehicle demand serves NS first; EW pedestrians must wait, so the
        # NS green must not start a walk for them.
        self.tick(1)
        out = self.tick(2, counts={"N": 5, "S": 5, "E": 0, "W": 0},
                        ped={"N": 0, "S": 0, "E": 4, "W": 0})
        self.assertEqual(out["phase"], "NS")
        self.assertFalse(out["walk_active"])

    def test_walk_holds_green_against_demand_switch(self):
        self.tick(1)
        self.tick(2, ped={"N": 2, "S": 0, "E": 0, "W": 0})
        # Heavy opposing demand would normally force a passage_gap switch
        # after min_green; the walk must hold the green instead. Ped demand
        # has already been served, so no extension re-arms the deadline.
        heavy = {"N": 0, "S": 0, "E": 40, "W": 40}
        for now in (5, 8):
            out = self.tick(now, counts=heavy)
            self.assertEqual(out["stage"], "GREEN")
            self.assertTrue(out["walk_active"])
            self.assertEqual(out["reason"], "pedestrian_walk")
            # walk_min (7s from GREEN entry at t=2) expires at t=9: switch resumes.
        out = self.tick(10, counts=heavy)
        self.assertEqual(out["stage"], "YELLOW")
        self.assertFalse(out["walk_active"])

    def test_walk_ends_after_walk_min_without_extension(self):
        self.tick(1)
        self.tick(2, ped={"N": 1, "S": 0, "E": 0, "W": 0})
        # Demand disappears: no extension, walk expires at entry + walk_min.
        out = self.tick(9.5, ped={"N": 0, "S": 0, "E": 0, "W": 0})
        self.assertFalse(out["walk_active"])
        self.assertNotEqual(out["reason"], "pedestrian_walk")

    def test_persistent_demand_extends_walk_up_to_walk_max(self):
        self.tick(1)
        self.tick(2, ped={"N": 5, "S": 0, "E": 0, "W": 0})
        ped = {"N": 5, "S": 0, "E": 0, "W": 0}
        heavy = {"N": 0, "S": 0, "E": 40, "W": 40}
        # Each tick within walk_max re-arms walk_min, so the walk persists
        # well past walk_min while demand keeps arriving.
        for now in (8.5, 14.5, 20.5, 21.5):
            out = self.tick(now, counts=heavy, ped=ped)
            self.assertEqual(out["stage"], "GREEN")
            self.assertTrue(out["walk_active"])
        # GREEN entry + walk_max (t=2+20=22) is a hard cap.
        out = self.tick(22.5, counts=heavy, ped=ped)
        self.assertFalse(out["walk_active"])

    def test_emergency_preemption_ends_walk(self):
        self.tick(1)
        self.tick(2, ped={"N": 2, "S": 0, "E": 0, "W": 0})
        self.c.request_preemption("E", 3)
        out = self.tick(3, ped={"N": 2, "S": 0, "E": 0, "W": 0})
        self.assertEqual(out["stage"], "YELLOW")
        self.assertEqual(out["reason"], "emergency_preemption")
        self.assertFalse(out["walk_active"])

    def test_sensor_loss_ends_walk(self):
        self.tick(1)
        self.tick(2, ped={"N": 2, "S": 0, "E": 0, "W": 0})
        obs = Observation.parse(v5(ped={"N": 2, "S": 0, "E": 0, "W": 0}), 1000)
        out = self.c.tick(6, obs, 2)  # received_at=2 -> stale at now=6
        self.assertEqual(out["stage"], "YELLOW")
        self.assertEqual(out["reason"], "sensor_unavailable")
        self.assertFalse(out["walk_active"])

    def test_maximum_green_ends_walk(self):
        self.tick(1)
        self.tick(2, ped={"N": 2, "S": 0, "E": 0, "W": 0})
        # max_green (60s) is a safety-class exit and outranks the walk hold.
        out = self.tick(63, ped={"N": 2, "S": 0, "E": 0, "W": 0})
        self.assertEqual(out["stage"], "YELLOW")
        self.assertEqual(out["reason"], "maximum_green")

    def test_yellow_and_all_red_durations_intact_during_walk(self):
        self.tick(1)
        self.tick(2, ped={"N": 2, "S": 0, "E": 0, "W": 0})
        self.c.request_preemption("E", 3)
        self.tick(3, ped={"N": 2, "S": 0, "E": 0, "W": 0})
        self.assertEqual(self.tick(5.99)["stage"], "YELLOW")
        self.assertEqual(self.tick(6)["stage"], "ALL_RED")
        self.assertEqual(self.tick(7.99)["stage"], "ALL_RED")
        self.assertEqual(self.tick(8)["stage"], "GREEN")

    def test_schema_v3_without_pedestrian_queue_does_not_crash(self):
        self.tick(1)
        out = self.tick(2, builder=v3)
        self.assertEqual(out["stage"], "GREEN")
        self.assertFalse(out["walk_active"])

    def test_snapshot_exposes_walk_active(self):
        self.tick(1)
        out = self.tick(2, ped={"N": 1, "S": 0, "E": 0, "W": 0})
        self.assertIn("walk_active", out)
        self.assertIs(out["walk_active"], True)


class WalkTimingTests(unittest.TestCase):
    def test_walk_fields_defaults_and_validation(self):
        timing = Timing()
        self.assertEqual(timing.walk_min, 7.0)
        self.assertEqual(timing.walk_max, 20.0)
        with self.assertRaises(ValueError):
            Timing(walk_min=0)
        with self.assertRaises(ValueError):
            Timing(walk_max=301)
        with self.assertRaises(ValueError):
            Timing(walk_min=25, walk_max=20)

    def test_small_max_green_still_accepted(self):
        # Walk fields must not reject compact test timings; max_green remains
        # the safety-class exit that ends any walk first at runtime.
        timing = Timing(min_green=.1, max_green=.8, yellow=.2, all_red=.1)
        self.assertEqual(timing.walk_max, 20.0)


class WalkRuntimeTests(unittest.TestCase):
    def test_walk_reason_is_journaled_as_transition_intent(self):
        now = [0.0]
        with tempfile.TemporaryDirectory() as directory:
            store = Store(str(Path(directory) / "state.db"))
            runtime = Runtime(store, Timing(max_tick_gap=100),
                              clock=lambda: now[0], wall=lambda: 1000)
            try:
                runtime.submit("camera", Observation.parse(v5(), 1000))
                runtime.tick()  # t=0 ALL_RED (startup clearance)
                now[0] = 1
                runtime.submit("camera", Observation.parse(v5(seq=2), 1000))
                runtime.tick()  # t=1 ALL_RED (all_red not yet elapsed)
                now[0] = 2
                runtime.submit("camera", Observation.parse(
                    v5(seq=3, ped={"N": 2, "S": 0, "E": 0, "W": 0}), 1000))
                runtime.tick()  # t=2 GREEN entry, walk scheduled
                now[0] = 3
                runtime.submit("camera", Observation.parse(
                    v5(seq=4, ped={"N": 2, "S": 0, "E": 0, "W": 0}), 1000))
                runtime.tick()  # t=3 walk reason change journaled
                rows = store.db.execute(
                    "SELECT payload FROM events WHERE kind='transition_intent'").fetchall()
                reasons = [json.loads(row[0])["reason"] for row in rows]
                self.assertIn("pedestrian_walk", reasons)
                walk_events = [json.loads(row[0]) for row in rows
                               if json.loads(row[0])["reason"] == "pedestrian_walk"]
                self.assertTrue(all(event["walk_active"] for event in walk_events))
            finally:
                runtime.close()


if __name__ == "__main__":
    unittest.main()