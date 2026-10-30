"""N x M grid network: conservation, coordination benefit, topology."""
import unittest

from sabz_edge.coordination import Coordinator
from sabz_edge.simulation import (GRID_LINK_S, grid_stream, grid_topology,
                                  simulate_grid)

SEEDS = (42, 307, 7)


def grid_mean_delay(coordinated, scale=0.7, duration=240):
    return sum(
        simulate_grid(seed=s, duration=duration, mode="max_pressure",
                      coordinated=coordinated, demand_scale=scale)["mean_delay_s"]
        for s in SEEDS
    ) / len(SEEDS)


class GridTopologyTests(unittest.TestCase):
    def test_two_by_two(self):
        nodes, links = grid_topology(2, 2)
        self.assertEqual(nodes, ["R0C0", "R0C1", "R1C0", "R1C1"])
        self.assertEqual(len(links), 8)   # 4 edges, both directions
        for u, d, travel in links:
            self.assertEqual(travel, GRID_LINK_S)
            self.assertIn(u, nodes)
            self.assertIn(d, nodes)

    def test_three_by_two_counts_edges(self):
        nodes, links = grid_topology(3, 2)
        self.assertEqual(len(nodes), 6)
        # 3 horizontal + 4 vertical undirected edges, each bidirectional
        self.assertEqual(len(links), 14)

    def test_bounds(self):
        for bad in ((1, 2), (2, 1), (5, 2), (2, 5)):
            with self.assertRaises(ValueError):
                grid_topology(*bad)

    def test_coordinator_accepts_grid_links(self):
        nodes, links = grid_topology(3, 3)
        c = Coordinator(offsets={n: 0.0 for n in nodes}, cycle_s=80.0, links=links)
        self.assertEqual(len(c.links), len(links))
        # route cost across a grid path uses observed/configured link travel
        self.assertAlmostEqual(c.route_cost(["R0C0", "R0C1", "R1C1"]),
                               2 * GRID_LINK_S, places=6)


class GridSimulationTests(unittest.TestCase):
    def test_conservation_across_modes(self):
        for coordinated in (False, True):
            for mode in ("fixed", "max_pressure"):
                r = simulate_grid(seed=42, duration=120, mode=mode,
                                  coordinated=coordinated, demand_scale=0.7)
                self.assertEqual(r["arrived"], r["exited"] + r["unfinished"],
                                 f"{mode} coordinated={coordinated}")

    def test_arrival_stream_is_reproducible(self):
        a = simulate_grid(seed=42, duration=60, coordinated=False)
        b = simulate_grid(seed=42, duration=60, coordinated=False)
        self.assertEqual(a["arrival_sha256"], b["arrival_sha256"])

    def test_coordinator_snapshot_only_when_coordinated(self):
        off = simulate_grid(seed=42, duration=60, coordinated=False)
        on = simulate_grid(seed=42, duration=60, coordinated=True)
        self.assertIsNone(off["coordinator"])
        self.assertIsNotNone(on["coordinator"])
        _, links = grid_topology(2, 2)
        self.assertEqual(len(on["coordinator"]["links"]), len(links))

    def test_coordinated_beats_independent_mean_delay(self):
        indep = grid_mean_delay(coordinated=False)
        coord = grid_mean_delay(coordinated=True)
        self.assertLessEqual(coord, indep,
                             f"coordinated {coord:.2f} worse than independent {indep:.2f}")

    def test_grid_run_records_link_travel_samples(self):
        r = simulate_grid(seed=42, duration=120, coordinated=True)
        costs = r["coordinator"]["link_costs"]
        self.assertTrue(costs)
        sampled = [c for c in costs.values() if c["samples"] > 0]
        self.assertTrue(sampled, "no grid link recorded travel samples")
        for c in sampled:
            self.assertAlmostEqual(c["observed"], GRID_LINK_S, places=3)

    def test_trace_records_all_nodes(self):
        r = simulate_grid(seed=42, duration=120, coordinated=True, trace=True)
        self.assertTrue(r["frames"])
        nodes, _ = grid_topology(2, 2)
        for frame in r["frames"]:
            for name in nodes:
                self.assertIn(name, frame["reason"])
                self.assertIn(name, frame["lamps"])

    def test_duration_bounds(self):
        with self.assertRaises(ValueError):
            simulate_grid(duration=10)
        with self.assertRaises(ValueError):
            simulate_grid(demand_scale=2.0)

    def test_stream_paths_stay_in_grid(self):
        stream = grid_stream(seed=1, duration=60, rows=2, cols=2)
        self.assertTrue(stream)
        for spawn, name, approach, exit_node in stream:
            self.assertNotEqual(name, exit_node)
            self.assertIn(name, ("R0C0", "R0C1", "R1C0", "R1C1"))
            self.assertIn(exit_node, ("R0C0", "R0C1", "R1C0", "R1C1"))


if __name__ == "__main__":
    unittest.main()