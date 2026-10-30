"""Idle and emission analytics in the historical report."""
import os
import tempfile
import unittest

from sabz_edge import report
from sabz_edge.core import VEHICLE_CLASSES
from sabz_edge.store import Store


def breakdown(**per_approach):
    """class_counts dict with zeros overridden by the given {approach: {class: n}}."""
    data = {a: dict.fromkeys(VEHICLE_CLASSES, 0) for a in "NSEW"}
    for approach, classes in per_approach.items():
        data[approach].update(classes)
    return data


class EmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "edge.sqlite3")
        self.store = Store(self.db)
        self.addCleanup(self.store.close)

    def summary(self):
        return report.summarize(report.load(self.db), now=1000.0)

    def test_idle_vehicle_seconds_and_co2_from_class_breakdowns(self):
        self.store.event("observation", {
            "schema_version": 6, "sequence": 1, "captured_at": 100.0,
            "counts": [5, 0, 0, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 5}),
        })
        self.store.event("observation", {
            "schema_version": 6, "sequence": 2, "captured_at": 110.0,
            "counts": [5, 0, 0, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 3, "bus": 1}),
        })
        idling = self.summary()["idling"]
        # First observation has no gap; the 10s gap before the second accrues
        # against the second observation's queue: 3 cars x 10s, 1 bus x 10s.
        self.assertEqual(idling["vehicle_s"]["car"], 30.0)
        self.assertEqual(idling["vehicle_s"]["bus"], 10.0)
        self.assertEqual(idling["vehicle_s"]["truck"], 0.0)
        self.assertEqual(idling["observations"], 1)
        self.assertEqual(idling["total_vehicle_s"], 40.0)
        self.assertAlmostEqual(idling["emissions_g"]["car"], 30.0 * 0.56, places=3)
        self.assertAlmostEqual(idling["emissions_g"]["bus"], 10.0 * 2.9, places=3)
        self.assertAlmostEqual(idling["total_emissions_g"],
                               30.0 * 0.56 + 10.0 * 2.9, places=3)
        self.assertEqual(idling["queue_vehicle_s"], 0.0)

    def test_first_observation_and_large_gaps_do_not_count_idle(self):
        self.store.event("observation", {
            "schema_version": 6, "sequence": 1, "captured_at": 100.0,
            "counts": [4, 0, 0, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 4}),
        })
        # 1000s later: the gap is clamped to the 60s cap, so only
        # 4 cars x 60s accrues (the first observation itself counts nothing).
        self.store.event("observation", {
            "schema_version": 6, "sequence": 2, "captured_at": 1100.0,
            "counts": [4, 0, 0, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 4}),
        })
        idling = self.summary()["idling"]
        self.assertEqual(idling["vehicle_s"]["car"], 240.0)
        self.assertEqual(idling["observations"], 1)

    def test_gap_cap_limits_idle_time(self):
        self.store.event("observation", {
            "schema_version": 6, "sequence": 1, "captured_at": 100.0,
            "counts": [2, 0, 0, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 2}),
        })
        self.store.event("observation", {
            "schema_version": 6, "sequence": 2, "captured_at": 160.0,
            "counts": [2, 0, 0, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 2}),
        })
        # 60s gap exactly at the cap: 2 cars x 60s = 120 veh-s.
        self.assertEqual(self.summary()["idling"]["vehicle_s"]["car"], 120.0)

    def test_observations_without_class_data_track_unclassified_idle(self):
        self.store.event("observation", {
            "schema_version": 5, "sequence": 1, "captured_at": 100.0,
            "counts": [6, 0, 0, 0], "conflict_clear": True, "healthy": True,
        })
        self.store.event("observation", {
            "schema_version": 5, "sequence": 2, "captured_at": 130.0,
            "counts": [6, 0, 0, 0], "conflict_clear": True, "healthy": True,
        })
        idling = self.summary()["idling"]
        self.assertEqual(idling["queue_vehicle_s"], 180.0)  # 6 x 30s
        self.assertEqual(idling["total_vehicle_s"], 0.0)
        self.assertEqual(idling["total_emissions_g"], 0.0)

    def test_render_contains_idle_table_and_hides_it_when_empty(self):
        self.store.event("observation", {
            "schema_version": 6, "sequence": 1, "captured_at": 100.0,
            "counts": [3, 0, 0, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 3}),
        })
        self.store.event("observation", {
            "schema_version": 6, "sequence": 2, "captured_at": 105.0,
            "counts": [3, 0, 0, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 3}),
        })
        text = report.render(self.summary())
        self.assertIn("idling & CO2 estimate", text)
        self.assertIn("veh-s", text)
        self.assertIn("car", text)
        self.assertIn("total", text)

                # A single observation has no gap: nothing to show.
        empty = tempfile.TemporaryDirectory()
        self.addCleanup(empty.cleanup)
        path = os.path.join(empty.name, "edge.sqlite3")
        store = Store(path)
        self.addCleanup(store.close)
        store.event("observation", {
            "schema_version": 6, "sequence": 1, "captured_at": 100.0,
            "counts": [3, 0, 0, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 3}),
        })
        text = report.render(report.summarize(report.load(path), now=1000.0))
        self.assertNotIn("idling & CO2 estimate", text)

    def test_render_reports_unclassified_idle_without_co2(self):
        self.store.event("observation", {
            "schema_version": 5, "sequence": 1, "captured_at": 100.0,
            "counts": [4, 0, 0, 0], "conflict_clear": True, "healthy": True,
        })
        self.store.event("observation", {
            "schema_version": 5, "sequence": 2, "captured_at": 120.0,
            "counts": [4, 0, 0, 0], "conflict_clear": True, "healthy": True,
        })
        text = report.render(self.summary())
        self.assertNotIn("idling & CO2 estimate", text)
        self.assertIn("unclassified stopped-vehicle idle: 80.0 veh-s", text)

    def test_json_summary_carries_idling_block(self):
        self.store.event("observation", {
            "schema_version": 6, "sequence": 1, "captured_at": 100.0,
            "counts": [2, 0, 0, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 2}),
        })
        self.store.event("observation", {
            "schema_version": 6, "sequence": 2, "captured_at": 110.0,
            "counts": [2, 0, 0, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 2}),
        })
        idling = self.summary()["idling"]
        self.assertEqual(set(idling["vehicle_s"]), set(VEHICLE_CLASSES))
        self.assertEqual(set(idling["emissions_g"]), set(VEHICLE_CLASSES))
        self.assertEqual(idling["vehicle_s"]["motorcycle"], 0.0)
        self.assertEqual(idling["emissions_g"]["bicycle"], 0.0)


if __name__ == "__main__":
    unittest.main()