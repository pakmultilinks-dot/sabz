import unittest

from sabz_edge.coordination import Coordinator, number
from sabz_edge.simulation import LINK_TRAVEL_S, simulate_corridor

SEEDS = (42, 307, 7)


def mean_delay(coordinated, scale=0.7, duration=600):
    return sum(
        simulate_corridor(seed=s, duration=duration, mode="max_pressure",
                          coordinated=coordinated, demand_scale=scale)["mean_delay_s"]
        for s in SEEDS
    ) / len(SEEDS)


class CoordinatorTests(unittest.TestCase):
    def test_cycle_s_bounds(self):
        for bad in (39, 201, float("nan"), "80"):
            with self.assertRaises(ValueError):
                Coordinator(cycle_s=bad)

    def test_link_travel_bounds(self):
        with self.assertRaises(ValueError):
            Coordinator(links=[("I0", "I1", 0)])
        with self.assertRaises(ValueError):
            Coordinator(links=[("I0", "I1", 500)])

    def test_offset_defaults_to_zero(self):
        self.assertEqual(Coordinator().offset("missing"), 0.0)
        self.assertEqual(Coordinator(offsets={"I1": 20}).offset("I1"), 20.0)

    def test_supply_hint_set_get_and_clear(self):
        c = Coordinator()
        c.set_supply_hint("I1", "NS", 0.5)
        self.assertEqual(c.supply_hint("I1", "NS"), 0.5)
        c.set_supply_hint("I1", "NS", None)
        self.assertIsNone(c.supply_hint("I1", "NS"))
        with self.assertRaises(ValueError):
            c.set_supply_hint("I1", "NS", 1.5)

    def test_release_drives_predicted_arrivals(self):
        c = Coordinator(links=[("I0", "I1", 20.0)])
        self.assertEqual(c.predicted_arrivals("I1", 0), {})
        c.note_release("I0", "NS", 100.0, size=8)
        # Platoon arrives at I1 at 120s: absent before, present at arrival.
        self.assertEqual(c.predicted_arrivals("I1", 110), {})
        self.assertEqual(c.predicted_arrivals("I1", 120), {"NS": 8})
        # Discharge window: 8 vehicles / 0.4 veh/s + 4s slack.
        self.assertEqual(c.predicted_arrivals("I1", 140), {"NS": 8})
        self.assertEqual(c.predicted_arrivals("I1", 160), {})

    def test_preferred_phase_none_without_platoon(self):
        c = Coordinator(links=[("I0", "I1", 20.0)])
        self.assertIsNone(c.preferred_phase("I1", 120))
        # Releases at I1 itself never feed I1's own preference.
        c.note_release("I1", "EW", 100.0, size=8)
        self.assertIsNone(c.preferred_phase("I1", 120))

    def test_preferred_phase_follows_platoon(self):
        c = Coordinator(links=[("I0", "I1", 20.0)])
        c.note_release("I0", "NS", 100.0, size=8)
        self.assertEqual(c.preferred_phase("I1", 121), "NS")
        self.assertIsNone(c.preferred_phase("I1", 200))

    def test_snapshot_exposes_topology_and_releases(self):
        c = Coordinator(offsets={"I1": 20}, links=[("I0", "I1", 20.0)])
        c.note_release("I0", "NS", 100.0, size=8)
        snap = c.snapshot()
        self.assertEqual(snap["offsets"], {"I1": 20})
        self.assertEqual(snap["links"], [["I0", "I1", 20.0]])
        self.assertEqual(snap["releases"], {"I0:NS": 100.0})

    def test_link_cost_defaults_to_configured_travel(self):
        c = Coordinator(links=[("I0", "I1", 20.0)])
        self.assertEqual(c.link_cost("I0", "I1"), 20.0)
        with self.assertRaises(ValueError):
            c.link_cost("I9", "I1")

    def test_arrival_samples_update_link_cost(self):
        c = Coordinator(links=[("I0", "I1", 20.0)])
        # Three samples at 30s: EWMA 20 -> 22.5 -> 24.375 -> 25.78125.
        for _ in range(3):
            self.assertTrue(c.note_arrival("I0", "I1", 100.0, 130.0))
        self.assertAlmostEqual(c.link_cost("I0", "I1"), 25.78125)
        # Implausible samples are ignored, not absorbed.
        self.assertFalse(c.note_arrival("I0", "I1", 100.0, 90.0))
        self.assertFalse(c.note_arrival("I0", "I1", 100.0, 500.0))
        self.assertAlmostEqual(c.link_cost("I0", "I1"), 25.78125)
        with self.assertRaises(ValueError):
            c.note_arrival("I9", "I1", 0.0, 1.0)

    def test_route_cost_sums_link_estimates(self):
        c = Coordinator(links=[("I0", "I1", 20.0), ("I1", "I2", 15.0)])
        c.note_arrival("I0", "I1", 0.0, 30.0)
        # I0->I1 EWMA: 20 + 0.25*(30-20) = 22.5; I1->I2 stays configured 15.
        self.assertAlmostEqual(c.route_cost(["I0", "I1", "I2"]), 22.5 + 15.0)
        with self.assertRaises(ValueError):
            c.route_cost(["I0"])

    def test_snapshot_exposes_link_costs(self):
        c = Coordinator(links=[("I0", "I1", 20.0)])
        snap = c.snapshot()
        self.assertEqual(snap["link_costs"]["I0:I1"],
                         {"configured": 20.0, "observed": None, "samples": 0})
        c.note_arrival("I0", "I1", 0.0, 25.0)
        snap = c.snapshot()
        self.assertEqual(snap["link_costs"]["I0:I1"]["samples"], 1)
        self.assertAlmostEqual(snap["link_costs"]["I0:I1"]["observed"], 21.25)

    def test_number_helper(self):
        self.assertEqual(number(5, "x", 1, 10), 5.0)
        with self.assertRaises(ValueError):
            number(0, "x", 1, 10)


class OffsetTuningTests(unittest.TestCase):
    """Closed-loop offset tuning: bounded, anchored to the plan, converging."""

    def _corridor(self, cycle=80.0, travel=20.0, offset=0.0):
        return Coordinator(offsets={"I1": offset}, cycle_s=cycle,
                           links=[("I0", "I1", travel)])

    def test_tune_moves_offset_toward_observed_travel(self):
        c = self._corridor()
        # One sample of 60s: EWMA 20 -> 30. Target = 30 % 80 = 30.
        self.assertTrue(c.note_arrival("I0", "I1", 0.0, 60.0))
        moved = c.tune_offsets(100.0)
        self.assertEqual(moved, {"I1": 4.0})  # one step, capped at 4s

    def test_tune_step_never_exceeds_four_seconds(self):
        c = self._corridor()
        c.note_arrival("I0", "I1", 0.0, 60.0)  # target 30
        now, prev = 100.0, 0.0
        for _ in range(3):
            now += 11.0
            moved = c.tune_offsets(now)
            self.assertEqual(len(moved), 1)
            self.assertLessEqual(abs(moved["I1"] - prev), 4.0 + 1e-9)
            prev = moved["I1"]

    def test_tune_converges_exactly_to_target(self):
        c = self._corridor()
        c.note_arrival("I0", "I1", 0.0, 60.0)  # target 30
        now, moved = 100.0, {"I1": 0.0}
        for _ in range(30):
            now += 11.0
            moved = c.tune_offsets(now)
            if not moved:
                break
        self.assertEqual(c.offset("I1"), 30.0)
        self.assertEqual(moved, {})  # converged: further tunes do nothing

    def test_tune_respects_min_interval(self):
        c = self._corridor()
        c.note_arrival("I0", "I1", 0.0, 60.0)
        self.assertEqual(c.tune_offsets(100.0), {"I1": 4.0})
        self.assertEqual(c.tune_offsets(105.0), {})   # 5s < 10s interval
        self.assertEqual(c.tune_offsets(110.0), {"I1": 8.0})

    def test_tune_wraps_shortest_way_round(self):
        c = self._corridor()
        # Sample of 220s: EWMA 20 -> 70. Target 70 is 10s *backwards*
        # from base 0 (wrap delta -10), so the offset must decrease.
        self.assertTrue(c.note_arrival("I0", "I1", 0.0, 220.0))
        now, moved = 100.0, {"I1": 0.0}
        for _ in range(30):
            now += 11.0
            moved = c.tune_offsets(now)
            if not moved:
                break
        self.assertEqual(c.offset("I1"), 70.0)  # -10 mod 80
        self.assertAlmostEqual(c.snapshot()["offset_adjustments"]["I1"], -10.0)

    def test_tune_never_exceeds_plan_deviation_cap(self):
        # cycle 160: cap = min(40, 80) = 40s from the configured plan.
        c = Coordinator(offsets={"I1": 0.0}, cycle_s=160.0,
                        links=[("I0", "I1", 80.0)])
        # Sample of 160s: EWMA 80 -> 100. Wrap delta from base 0 is -60,
        # but the plan cap clamps it to -40.
        self.assertTrue(c.note_arrival("I0", "I1", 0.0, 160.0))
        now = 100.0
        for _ in range(40):
            now += 11.0
            if not c.tune_offsets(now):
                break
        self.assertAlmostEqual(c.snapshot()["offset_adjustments"]["I1"], -40.0)

    def test_tune_uses_circular_mean_for_multi_inbound_node(self):
        c = Coordinator(offsets={"I2": 0.0}, cycle_s=80.0,
                        links=[("I0", "I2", 20.0), ("I1", "I2", 20.0)])
        c.note_arrival("I0", "I2", 0.0, 40.0)   # cost 25 -> target 25
        c.note_arrival("I1", "I2", 0.0, 120.0)  # cost 45 -> target 45
        now = 100.0
        for _ in range(30):
            now += 11.0
            if not c.tune_offsets(now):
                break
        # Circular mean of 25 and 45 is 35.
        self.assertEqual(c.offset("I2"), 35.0)

    def test_tune_skips_nodes_without_incoming_links(self):
        c = Coordinator(offsets={"I1": 10.0}, cycle_s=80.0, links=[])
        self.assertEqual(c.tune_offsets(100.0), {})
        self.assertEqual(c.offset("I1"), 10.0)

    def test_snapshot_reports_adjustments_from_plan(self):
        c = self._corridor()
        self.assertEqual(c.snapshot()["offset_adjustments"], {"I1": 0.0})
        c.note_arrival("I0", "I1", 0.0, 60.0)
        c.tune_offsets(100.0)
        self.assertEqual(c.snapshot()["offset_adjustments"], {"I1": 4.0})

    def test_tune_validates_arguments(self):
        c = self._corridor()
        with self.assertRaises(ValueError):
            c.tune_offsets(-1.0)
        with self.assertRaises(ValueError):
            c.tune_offsets(100.0, min_interval_s=0.5)


class CorridorSimulationTests(unittest.TestCase):
    def test_conservation_across_modes(self):
        for coordinated in (False, True):
            for mode in ("fixed", "max_pressure"):
                r = simulate_corridor(seed=42, duration=120, mode=mode,
                                      coordinated=coordinated, demand_scale=0.7)
                self.assertEqual(r["arrived"],
                                 r["exited"] + r["unfinished"],
                                 f"{mode} coordinated={coordinated}")

    def test_arrival_stream_is_reproducible(self):
        a = simulate_corridor(seed=42, duration=60, coordinated=False)
        b = simulate_corridor(seed=42, duration=60, coordinated=False)
        self.assertEqual(a["arrival_sha256"], b["arrival_sha256"])

    def test_coordinator_snapshot_only_when_coordinated(self):
        off = simulate_corridor(seed=42, duration=60, coordinated=False)
        on = simulate_corridor(seed=42, duration=60, coordinated=True)
        self.assertIsNone(off["coordinator"])
        self.assertIsNotNone(on["coordinator"])
        self.assertEqual(on["coordinator"]["links"],
                         [["I0", "I1", LINK_TRAVEL_S]])

    def test_trace_records_switch_reasons(self):
        r = simulate_corridor(seed=42, duration=120, coordinated=True, trace=True)
        self.assertTrue(r["frames"])
        for frame in r["frames"]:
            self.assertIn("reason", frame)
            self.assertIn("I0", frame["reason"])
            self.assertIn("I1", frame["reason"])

    def test_coordinated_beats_independent_mean_delay(self):
        indep = mean_delay(coordinated=False)
        coord = mean_delay(coordinated=True)
        self.assertLessEqual(coord, indep,
                             f"coordinated {coord:.2f} worse than independent {indep:.2f}")

    def test_corridor_run_records_link_travel_samples(self):
        r = simulate_corridor(seed=42, duration=120, coordinated=True)
        costs = r["coordinator"]["link_costs"]
        self.assertIn("I0:I1", costs)
        self.assertEqual(costs["I0:I1"]["configured"], LINK_TRAVEL_S)
        # Simulated link travel is exactly LINK_TRAVEL_S, so the observed
        # estimate must converge to it once platoons have crossed.
        self.assertGreater(costs["I0:I1"]["samples"], 0)
        self.assertAlmostEqual(costs["I0:I1"]["observed"], LINK_TRAVEL_S, places=3)

    def test_duration_bounds(self):
        with self.assertRaises(ValueError):
            simulate_corridor(duration=10)
        with self.assertRaises(ValueError):
            simulate_corridor(demand_scale=2.0)


if __name__ == "__main__":
    unittest.main()