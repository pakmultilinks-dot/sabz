import unittest

from sabz_edge.adaptive import MaxPressurePolicy
from sabz_edge.core import Controller, Observation, Timing
from sabz_edge.simulation import arrival_stream, simulate
from test_adaptive import obs, packet


class MaxPressurePolicyTests(unittest.TestCase):
    def test_mode_is_accepted_and_unknown_mode_still_rejected(self):
        controller = Controller(Timing(), 0, mode="max_pressure")
        self.assertEqual(controller.mode, "max_pressure")
        with self.assertRaises(ValueError):
            Controller(Timing(), 0, mode="greedy")

    def test_pressure_is_upstream_queue_minus_downstream_queue(self):
        policy = MaxPressurePolicy()
        details = policy.inspect(obs(counts=(10, 8, 2, 2), downstream=(4, 4, 0, 0)), 0)
        self.assertEqual(details["NS"]["pressure"], 10 + 8 - 4 - 4)
        self.assertEqual(details["EW"]["pressure"], 2 + 2)

    def test_switches_when_opposing_pressure_exceeds_current_by_margin(self):
        policy = MaxPressurePolicy()
        policy.inspect(obs(counts=(2, 2, 20, 20)), 0)
        self.assertEqual(policy.switch_reason("NS", "EW", 10, 10), "pressure_difference")
        self.assertEqual(policy.next_phase("NS"), "EW")

    def test_hysteresis_margin_prevents_thrashing(self):
        policy = MaxPressurePolicy()
        # Pressure gap of exactly 1 equals the switch margin: hold.
        policy.inspect(obs(counts=(10, 10, 10, 11)), 0)
        self.assertIsNone(policy.switch_reason("NS", "EW", 25, 25))
        # Gap of 2 exceeds the margin once the batching target green is met.
        policy.inspect(obs(counts=(10, 10, 11, 11)), 1)
        self.assertEqual(policy.switch_reason("NS", "EW", 25, 25), "pressure_difference")

    def test_blocked_downstream_abandons_the_current_phase(self):
        policy = MaxPressurePolicy()
        policy.inspect(obs(counts=(5, 5, 40, 40), downstream=(20, 20, 0, 0)), 0)
        # NS cannot discharge (downstream full): leave it for the servable EW.
        self.assertEqual(policy.switch_reason("NS", "EW", 10, 10), "downstream_blocked")
        self.assertEqual(policy.next_phase("NS"), "EW")

    def test_fully_blocked_intersection_holds_in_clearance(self):
        policy = MaxPressurePolicy()
        policy.inspect(obs(counts=(5, 5, 40, 40), downstream=(20, 20, 20, 20)), 0)
        self.assertIsNone(policy.next_phase("NS"))

    def test_blocked_opposing_group_never_steals_the_green(self):
        policy = MaxPressurePolicy()
        policy.inspect(obs(counts=(1, 1, 50, 50), downstream=(0, 0, 20, 20)), 0)
        self.assertIsNone(policy.switch_reason("NS", "EW", 10, 10))

    def test_min_green_stays_outside_the_optimizer(self):
        controller = Controller(Timing(max_tick_gap=100), 0, mode="max_pressure")
        controller.tick(2, obs(counts=(1, 1, 0, 0)), 2)
        demand = obs(counts=(0, 0, 70, 70))
        self.assertEqual(controller.tick(3, demand, 3)["stage"], "GREEN")
        self.assertEqual(controller.tick(10, demand, 10)["stage"], "YELLOW")

    def test_snapshot_reports_max_pressure_algorithm(self):
        controller = Controller(Timing(max_tick_gap=100), 0, mode="max_pressure")
        state = controller.tick(2, obs(counts=(5, 5, 1, 1)), 2)
        self.assertEqual(state["algorithm"], "max-pressure-v1")
        self.assertIn("pressure", state["phase_scores"]["NS"])

    def test_safety_kernel_still_owns_transitions(self):
        controller = Controller(Timing(max_tick_gap=100), 0, mode="max_pressure")
        controller.tick(2, obs(counts=(70, 0, 1, 0)), 2)
        # Demand shifts to EW, but a 70m vehicle on the served N approach
        # must block the max-pressure switch.
        data = packet(counts=(1, 0, 70, 0))
        data.update(schema_version=3, nearest_moving_distance_m=dict.fromkeys("NSEW", None),
                    max_approach_speed_mps=dict.fromkeys("NSEW", 0),
                    distance_uncertainty_m=dict.fromkeys("NSEW", 1))
        data["nearest_moving_distance_m"]["N"] = 50
        data["max_approach_speed_mps"]["N"] = 12
        state = controller.tick(10, Observation.parse(data, 1000), 10)
        self.assertEqual(state["stage"], "GREEN")
        self.assertEqual(state["reason"], "approach_protection_70m")


class MaxPressureBenchmarkTests(unittest.TestCase):
    def test_all_modes_conserve_vehicles_on_identical_arrivals(self):
        stream = arrival_stream("tidal", 307, 240)
        results = [simulate("tidal", 307, 240, mode, stream=stream, trace=False)
                   for mode in ("fixed", "actuated", "adaptive", "max_pressure")]
        self.assertEqual(len({r["arrival_sha256"] for r in results}), 1)
        for result in results:
            self.assertEqual(result["arrived"], result["served"] + result["unfinished"])
            self.assertGreaterEqual(result["accrued_delay_s"], 0)

    def test_max_pressure_beats_fixed_plan_on_tidal_demand(self):
        stream = arrival_stream("tidal", 307, 240)
        fixed = simulate("tidal", 307, 240, "fixed", stream=stream, trace=False)
        mp = simulate("tidal", 307, 240, "max_pressure", stream=stream, trace=False)
        self.assertLess(mp["mean_delay_s"], fixed["mean_delay_s"])
        self.assertLessEqual(mp["unfinished"], fixed["unfinished"])

    def test_max_pressure_is_competitive_with_adaptive_across_scenarios(self):
        for scenario in ("tidal", "balanced", "bursts"):
            with self.subTest(scenario=scenario):
                stream = arrival_stream(scenario, 42, 240)
                adaptive = simulate(scenario, 42, 240, "adaptive", stream=stream, trace=False)
                mp = simulate(scenario, 42, 240, "max_pressure", stream=stream, trace=False)
                self.assertLess(mp["mean_delay_s"], adaptive["mean_delay_s"] * 1.15)


if __name__ == "__main__":
    unittest.main()