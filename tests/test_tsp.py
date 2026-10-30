"""Transit signal priority: bounded green hold for queued buses."""
import unittest

from sabz_edge.core import Controller, Observation, Timing

from test_class_breakdown import breakdown, v6
from test_edge import payload


def bus_packet(bus_on=("N",), waits=(0, 0, 60, 0), counts=(1, 0, 5, 0),
               distance=None, speed=0.0):
    """Schema-v6 packet: buses on `bus_on` approaches, EW waiting 60s so the
    policy would otherwise switch away from NS at min-green."""
    data = v6(class_counts=breakdown(**{a: {"bus": 1} for a in bus_on}))
    data["counts"] = dict(zip("NSEW", counts))
    data["oldest_wait_s"] = dict(zip("NSEW", waits))
    if distance is not None:
        data["nearest_moving_distance_m"]["N"] = distance
        data["max_approach_speed_mps"]["N"] = speed
    return data


class TSPTests(unittest.TestCase):
    def setUp(self):
        self.c = Controller(Timing(max_tick_gap=100), 0)

    def tick(self, now, data=None):
        data = payload() if data is None else data
        data["captured_at"] = now
        return self.c.tick(now, Observation.parse(data, now), now)

    def start_green(self):
        self.assertEqual(self.tick(1)["stage"], "ALL_RED")
        self.assertEqual(self.tick(2)["stage"], "GREEN")

    def test_bus_holds_green_past_min_green(self):
        self.start_green()
        out = self.tick(10, bus_packet())
        self.assertEqual(out["stage"], "GREEN")
        self.assertEqual(out["reason"], "tsp_extended")
        self.assertEqual(out["tsp_hold_until"], 25.0)

    def test_no_bus_switches_at_min_green(self):
        self.start_green()
        out = self.tick(10, bus_packet(bus_on=()))
        self.assertEqual(out["stage"], "YELLOW")
        self.assertEqual(out["reason"], "waiting_time_priority")

    def test_bus_on_opposing_approach_does_not_hold(self):
        self.start_green()
        out = self.tick(10, bus_packet(bus_on=("E",)))
        self.assertEqual(out["stage"], "YELLOW")
        self.assertEqual(out["reason"], "waiting_time_priority")

    def test_hold_releases_after_bus_departs(self):
        self.start_green()
        self.assertEqual(self.tick(10, bus_packet())["stage"], "GREEN")
        out = self.tick(13, bus_packet(bus_on=()))
        self.assertEqual(out["stage"], "GREEN")
        self.assertEqual(out["reason"], "tsp_extended")
        out = self.tick(28, bus_packet(bus_on=()))
        self.assertEqual(out["stage"], "YELLOW")
        self.assertEqual(out["reason"], "waiting_time_priority")

    def test_maximum_green_overrides_tsp(self):
        self.start_green()
        out = self.tick(62, bus_packet())
        self.assertEqual(out["stage"], "YELLOW")
        self.assertEqual(out["reason"], "maximum_green")

    def test_approach_protection_display_wins_over_tsp(self):
        self.start_green()
        out = self.tick(10, bus_packet(distance=50, speed=10))
        self.assertEqual(out["stage"], "GREEN")
        self.assertEqual(out["reason"], "approach_protection_70m")

    def test_emergency_preemption_not_held(self):
        self.start_green()
        self.c.preempt_request = ("E", 10)
        out = self.tick(10, bus_packet())
        self.assertEqual(out["stage"], "YELLOW")
        self.assertEqual(out["reason"], "emergency_preemption")

    def test_schema_v1_min_green_contract_intact(self):
        # v1 payloads carry no class_counts, so TSP is inert by construction.
        self.start_green()
        self.assertEqual(self.tick(9, payload(counts={"N": 0, "S": 0, "E": 30, "W": 0}))["stage"], "GREEN")
        self.assertEqual(self.tick(10, payload(counts={"N": 0, "S": 0, "E": 30, "W": 0}))["stage"], "YELLOW")

    def test_timing_validation(self):
        with self.assertRaises(ValueError):
            Timing(tsp_extension_s=-1)
        with self.assertRaises(ValueError):
            Timing(tsp_extension_s=121)

    def test_snapshot_exposes_tsp_state(self):
        self.start_green()
        out = self.tick(10, bus_packet())
        self.assertIn("tsp_hold_until", out)
        self.assertEqual(out["tsp_hold_until"], 25.0)


if __name__ == "__main__":
    unittest.main()