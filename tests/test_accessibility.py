"""Accessibility-aware timing: per-approach multipliers for walk and green."""
import unittest

from sabz_edge.core import Controller, Observation, Timing

from test_walk import v5


class AccessibilityTimingTests(unittest.TestCase):
    def test_default_is_empty_and_neutral(self):
        timing = Timing()
        self.assertEqual(timing.accessibility, {})
        c = Controller(timing, 0)
        self.assertEqual(c.accessibility_factor("NS"), 1.0)
        self.assertEqual(c.accessibility_factor("EW"), 1.0)

    def test_validation_rejects_bad_config(self):
        with self.assertRaises(ValueError):
            Timing(accessibility={"X": 1.5})          # unknown approach
        with self.assertRaises(ValueError):
            Timing(accessibility={"N": 0.5})          # below 1.0
        with self.assertRaises(ValueError):
            Timing(accessibility={"N": 3.1})          # above 3.0
        with self.assertRaises(ValueError):
            Timing(accessibility="N=1.5")             # not a mapping
        Timing(accessibility={"N": 1.5, "E": 2.0})    # valid

    def test_factor_uses_max_of_phase_approaches(self):
        c = Controller(Timing(accessibility={"N": 1.5}), 0)
        self.assertEqual(c.accessibility_factor("NS"), 1.5)
        self.assertEqual(c.accessibility_factor("EW"), 1.0)

    def test_timing_file_round_trip(self):
        # server.py builds Timing(**load_json(...)) from SABZ_TIMING_FILE.
        config = {"min_green": 8.0, "accessibility": {"N": 1.5}}
        timing = Timing(**config)
        self.assertEqual(timing.accessibility, {"N": 1.5})


class AccessibilityWalkTests(unittest.TestCase):
    def setUp(self):
        self.ped_n = {"N": 3, "S": 0, "E": 0, "W": 0}
        self.ped_e = {"N": 0, "S": 0, "E": 3, "W": 0}

    def tick(self, c, now, **kw):
        obs = Observation.parse(v5(**kw), 1000)
        return c.tick(now, obs, now)

    def test_walk_min_scales_on_flagged_approach(self):
        c = Controller(Timing(max_tick_gap=100, accessibility={"N": 1.5}), 0)
        self.tick(c, 1)
        out = self.tick(c, 2, ped=self.ped_n)
        self.assertTrue(out["walk_active"])
        # walk_min 7 * 1.5 = 10.5 -> walk_until = 12.5 (entry at t=2).
        self.assertEqual(c.walk_until, 12.5)
        # Demand disappears, so no extension re-arms the deadline.
        out = self.tick(c, 11, ped={"N": 0, "S": 0, "E": 0, "W": 0})
        self.assertTrue(out["walk_active"])
        out = self.tick(c, 13, ped={"N": 0, "S": 0, "E": 0, "W": 0})
        self.assertFalse(out["walk_active"])

    def test_walk_unchanged_on_unflagged_phase(self):
        c = Controller(Timing(max_tick_gap=100, accessibility={"N": 1.5}), 0)
        self.tick(c, 1)
        self.tick(c, 2, counts={"E": 5, "W": 5, "N": 0, "S": 0}, ped=self.ped_e)
        # EW phase is unflagged: walk_min stays 7s -> walk_until = 9.0.
        self.assertEqual(c.walk_until, 9.0)

    def test_walk_extension_cap_scales(self):
        c = Controller(Timing(max_tick_gap=100, accessibility={"N": 1.5}), 0)
        self.tick(c, 1)
        self.tick(c, 2, ped=self.ped_n)
        heavy = {"N": 0, "S": 0, "E": 40, "W": 40}
        # Each tick lands inside the previous deadline, so the walk keeps
        # re-arming until the cap: entry + walk_max * 1.5 = 2 + 30 = 32.
        for now in (11, 21, 31):
            out = self.tick(c, now, counts=heavy, ped=self.ped_n)
            self.assertTrue(out["walk_active"])
        out = self.tick(c, 33, counts=heavy, ped=self.ped_n)
        self.assertFalse(out["walk_active"])


class AccessibilityGreenTests(unittest.TestCase):
    def tick(self, c, now, **kw):
        obs = Observation.parse(v5(**kw), 1000)
        return c.tick(now, obs, now)

    def test_min_green_scales_on_flagged_phase(self):
        heavy = {"N": 0, "S": 0, "E": 40, "W": 40}
        # Baseline: min_green 8s from entry at t=2 -> switch possible at t=10.
        base = Controller(Timing(max_tick_gap=100), 0)
        self.tick(base, 1)
        self.tick(base, 2, counts={"N": 5, "S": 5, "E": 0, "W": 0})
        out = self.tick(base, 10, counts=heavy)
        self.assertEqual(out["stage"], "YELLOW")
        # Flagged: min_green 8 * 1.5 = 12s -> still GREEN at t=13, switch at t=15.
        c = Controller(Timing(max_tick_gap=100, accessibility={"N": 1.5}), 0)
        self.tick(c, 1)
        self.tick(c, 2, counts={"N": 5, "S": 5, "E": 0, "W": 0})
        out = self.tick(c, 13, counts=heavy)
        self.assertEqual(out["stage"], "GREEN")
        out = self.tick(c, 15, counts=heavy)
        self.assertEqual(out["stage"], "YELLOW")

    def test_max_green_scales_on_flagged_phase(self):
        # Baseline trips maximum_green at elapsed >= 60 (entry t=2 -> t=62).
        base = Controller(Timing(max_tick_gap=100), 0)
        self.tick(base, 1)
        self.tick(base, 2)
        out = self.tick(base, 63)
        self.assertEqual(out["reason"], "maximum_green")
        # Flagged: max_green 60 * 1.5 = 90 -> GREEN at t=63, trips at t=94.
        c = Controller(Timing(max_tick_gap=100, accessibility={"N": 1.5}), 0)
        self.tick(c, 1)
        self.tick(c, 2)
        out = self.tick(c, 63)
        self.assertEqual(out["stage"], "GREEN")
        self.assertNotEqual(out["reason"], "maximum_green")
        out = self.tick(c, 94)
        self.assertEqual(out["reason"], "maximum_green")

    def test_snapshot_exposes_accessibility(self):
        c = Controller(Timing(max_tick_gap=100, accessibility={"N": 1.5}), 0)
        out = self.tick(c, 1)
        self.assertEqual(out["accessibility"], {"N": 1.5})
        base = Controller(Timing(max_tick_gap=100), 0)
        self.assertEqual(self.tick(base, 1)["accessibility"], {})


if __name__ == "__main__":
    unittest.main()