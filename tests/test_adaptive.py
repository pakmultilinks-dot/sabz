import unittest

from sabz_edge.adaptive import AdaptivePolicy
from sabz_edge.core import Controller, Observation, Timing
from sabz_edge.cabinet_model import Guard
from sabz_edge.simulation import SCENARIOS, arrival_stream, simulate
import test_edge as fixtures


def packet(counts=(10, 10, 2, 2), downstream=(0, 0, 0, 0), waits=(0, 0, 0, 0), approaching=(0, 0, 0, 0)):
    data = fixtures.payload(counts=dict(zip("NSEW", counts)))
    data.update(schema_version=2, downstream_counts=dict(zip("NSEW", downstream)),
                downstream_capacity=dict.fromkeys("NSEW", 20), approaching=dict(zip("NSEW", approaching)),
                arrival_rate=dict.fromkeys("NSEW", 0), oldest_wait_s=dict(zip("NSEW", waits)))
    return data


def obs(**kw):
    return Observation.parse(packet(**kw), 1000)


class AdaptiveTests(unittest.TestCase):
    def test_largest_raw_queue_does_not_win_if_receiving_roads_full(self):
        policy = AdaptivePolicy()
        details = policy.inspect(obs(counts=(80, 80, 3, 3), downstream=(20, 20, 0, 0)), 0)
        self.assertEqual(details["NS"]["score"], 0)
        self.assertEqual(policy.next_phase("NS"), "EW")

    def test_waiting_time_priority_overrides_pressure(self):
        policy = AdaptivePolicy()
        policy.inspect(obs(counts=(80, 80, 1, 0), waits=(0, 0, 65, 0)), 0)
        self.assertEqual(policy.next_phase("NS"), "EW")
        self.assertEqual(policy.switch_reason("NS", "EW", 0), "waiting_time_priority")

    def test_old_individual_wait_does_not_force_short_cycles_after_service(self):
        policy = AdaptivePolicy()
        policy.inspect(obs(counts=(100,100,100,100), waits=(200,200,200,200)), 100)
        policy.mark_service_opportunity("EW", 95)
        self.assertIsNone(policy.switch_reason("NS", "EW", 100, 8))
        self.assertEqual(policy.switch_reason("NS", "EW", 156, 8), "waiting_time_priority")

    def test_passage_gap_does_not_cut_immediately(self):
        policy = AdaptivePolicy()
        policy.inspect(obs(counts=(1, 0, 0, 0)), 0)
        policy.inspect(obs(counts=(0, 0, 1, 0)), 1)
        self.assertIsNone(policy.switch_reason("NS", "EW", 1))
        policy.inspect(obs(counts=(0, 0, 1, 0)), 3)
        self.assertEqual(policy.switch_reason("NS", "EW", 3), "passage_gap")

    def test_batching_accounts_for_clearance_cost(self):
        data = packet(counts=(4, 4, 10, 10))
        data["arrival_rate"] = dict.fromkeys("NSEW", .18)
        policy = AdaptivePolicy()
        policy.inspect(Observation.parse(data, 1000), 0)
        self.assertGreater(policy.details["NS"]["target_green_s"], 8)
        self.assertIsNone(policy.switch_reason("NS", "EW", 8, 8))
        self.assertEqual(policy.switch_reason("NS", "EW", 35, 35), "pressure_difference")

    def test_both_receiving_groups_full_hold_all_red(self):
        controller = Controller(Timing(max_tick_gap=100), 0)
        observation = obs(downstream=(20, 20, 20, 20))
        state = controller.tick(2, observation, 2)
        self.assertEqual(state["stage"], "ALL_RED")
        self.assertEqual(state["reason"], "downstream_blocked")

    def test_minimum_green_remains_outside_optimizer(self):
        controller = Controller(Timing(max_tick_gap=100), 0)
        controller.tick(2, obs(), 2)
        demand = obs(counts=(0, 0, 70, 70))
        self.assertEqual(controller.tick(3, demand, 3)["stage"], "GREEN")
        self.assertEqual(controller.tick(10, demand, 10)["stage"], "YELLOW")

    def test_cabinet_permits_candidate_selection_only_after_clearance(self):
        cabinet = Guard(Timing(), 0)
        base = {"command_sequence": 1, "lease_s": .5, "stage": "GREEN", "phase": "EW",
                "lamps": {"N": "RED", "S": "RED", "E": "GREEN", "W": "GREEN"}}
        self.assertEqual(cabinet.accept(base, 1)["stage"], "ALL_RED")
        # Keep the lease alive throughout startup.
        for seq, now in enumerate((1.25, 1.5, 1.75, 2), start=2):
            result = cabinet.accept(dict(base, command_sequence=seq), now)
        self.assertEqual(result["stage"], "GREEN")
        self.assertEqual(result["phase"], "EW")

    def test_v2_strict_fields_and_capacity_bounds(self):
        for field, value in (("arrival_rate", 6), ("downstream_capacity", 0), ("oldest_wait_s", -1), ("approaching", True)):
            data = packet(); data[field]["N"] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                Observation.parse(data, 1000)
        data = packet(downstream=(21, 0, 0, 0))
        with self.assertRaises(ValueError):
            Observation.parse(data, 1000)

    def test_v1_is_compatible_and_does_not_invent_downstream_measurements(self):
        observation = Observation.parse(fixtures.payload(), 1000)
        self.assertEqual(observation.schema_version, 1)
        self.assertEqual(observation.downstream_counts, ())

    def test_comparisons_share_exact_arrivals_and_conserve_vehicles(self):
        for scenario in SCENARIOS:
            stream = arrival_stream(scenario, 307, 240)
            results = [simulate(scenario, 307, 240, mode, stream=stream, trace=False) for mode in ("fixed", "actuated", "adaptive")]
            self.assertEqual(len({r["arrival_sha256"] for r in results}), 1)
            for result in results:
                self.assertEqual(result["arrived"], result["served"] + result["unfinished"])
                self.assertGreaterEqual(result["accrued_delay_s"], 0)

    def test_dynamic_demand_produces_new_not_replayed_traffic(self):
        low = simulate("balanced", 888, 60, demand_scale=.5)
        high = simulate("balanced", 888, 60, demand_scale=1.5)
        self.assertNotEqual(low["arrival_sha256"], high["arrival_sha256"])
        self.assertGreater(high["arrived"], low["arrived"])


class AdaptiveHTTPTests(unittest.TestCase):
    setUp = fixtures.HTTPTests.setUp
    tearDown = fixtures.HTTPTests.tearDown
    request = fixtures.HTTPTests.request

    def test_version_two_reaches_supported_integration_runtime(self):
        import time
        data = packet(); data["captured_at"] = time.time()
        code, _ = self.request("POST", "/v1/observations", data, "c" * 32)
        self.assertEqual(code, 202)
        time.sleep(.12)
        _, state = self.request("GET", "/v1/status", token="r" * 32)
        self.assertEqual(state["controller"]["algorithm"], "capacity-aware-adaptive-v1")
        self.assertIn("NS", state["controller"]["phase_scores"])
        import json
        stored = json.loads(self.store.db.execute("SELECT payload FROM events WHERE kind='observation'").fetchone()[0])
        self.assertEqual(stored["schema_version"], 2)
        self.assertEqual(len(stored["downstream_counts"]), 4)


if __name__ == "__main__":
    unittest.main()
