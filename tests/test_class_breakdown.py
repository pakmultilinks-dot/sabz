"""Schema v6 stopped-vehicle class breakdown: parse, client, perception, report."""
import json
import os
import tempfile
import unittest
from pathlib import Path

from sabz_edge.client import CameraClient
from sabz_edge.core import Observation, VEHICLE_CLASSES
from sabz_edge.perception import Detection, MetricProducer, RoadPlane
from sabz_edge import report
from sabz_edge.store import Store

import test_edge as fixtures
from test_edge import HTTPTests, payload


def v6(seq=1, stamp=1000, class_counts=None):
    data = payload(seq=seq, stamp=stamp)
    data.update({"schema_version": 6,
                 "downstream_counts": dict.fromkeys("NSEW", 0),
                 "downstream_capacity": dict.fromkeys("NSEW", 100),
                 "approaching": dict.fromkeys("NSEW", 0),
                 "arrival_rate": dict.fromkeys("NSEW", 0),
                 "oldest_wait_s": dict.fromkeys("NSEW", 0),
                 "nearest_moving_distance_m": dict.fromkeys("NSEW", None),
                 "max_approach_speed_mps": dict.fromkeys("NSEW", 0),
                 "distance_uncertainty_m": dict.fromkeys("NSEW", 0),
                 "pedestrian_queue": dict.fromkeys("NSEW", 0),
                 "emergency": dict.fromkeys("NSEW", 0),
                 "class_counts": class_counts if class_counts is not None else
                                  {a: dict.fromkeys(VEHICLE_CLASSES, 0) for a in "NSEW"}})
    return data


def breakdown(**per_approach):
    """class_counts dict with zeros overridden by the given {approach: {class: n}}."""
    data = {a: dict.fromkeys(VEHICLE_CLASSES, 0) for a in "NSEW"}
    for approach, classes in per_approach.items():
        data[approach].update(classes)
    return data


class ParseTests(unittest.TestCase):
    def test_v6_round_trip_and_v1_to_v5_backward_compatibility(self):
        counts = breakdown(N={"car": 3, "motorcycle": 1}, E={"bus": 2, "bicycle": 1})
        obs = Observation.parse(v6(class_counts=counts), 1000)
        self.assertEqual(obs.schema_version, 6)
        self.assertEqual(obs.class_counts[0]["car"], 3)
        self.assertEqual(obs.class_counts[0]["motorcycle"], 1)
        self.assertEqual(obs.class_counts[2]["bus"], 2)
        self.assertEqual(obs.class_counts[2]["bicycle"], 1)
        self.assertEqual(obs.class_counts[1]["car"], 0)
        for version in (1, 2, 3, 4, 5):
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
            if version >= 5:
                data.update({"schema_version": 5,
                             "emergency": dict.fromkeys("NSEW", 0)})
            data["schema_version"] = version
            self.assertEqual(Observation.parse(data, 1000).schema_version, version)

    def test_v6_rejects_bad_class_breakdowns(self):
        missing_approach = {a: dict.fromkeys(VEHICLE_CLASSES, 0) for a in "NSE"}
        person_vocabulary = {a: dict.fromkeys(
            ("car", "motorcycle", "bicycle", "bus", "person"), 0) for a in "NSEW"}
        extra_key = breakdown()
        extra_key["X"] = dict.fromkeys(VEHICLE_CLASSES, 0)
        for bad in (
            missing_approach,               # approach W absent
            person_vocabulary,              # person instead of truck
            extra_key,                      # unknown approach X
            breakdown(N={"car": 1.5}),      # non-whole number
            breakdown(N={"car": -1}),       # negative
            breakdown(N={"car": 501}),      # above cap
            breakdown(N={"car": True}),     # bool is not a count
        ):
            with self.assertRaises(ValueError):
                Observation.parse(v6(class_counts=bad), 1000)
        missing = v6()
        del missing["class_counts"]
        with self.assertRaises(ValueError):
            Observation.parse(missing, 1000)
        extra = v6()
        extra["class_totals"] = {}
        with self.assertRaises(ValueError):
            Observation.parse(extra, 1000)


def calibration():
    return RoadPlane([(0, 0), (100, 0), (100, 200), (0, 200)],
                     [(0, 200), (10, 200), (10, 0), (0, 0)],
                     width_m=10, length_m=200, uncertainty_m=1)


class PerceptionTests(unittest.TestCase):
    def setUp(self):
        self.producer = MetricProducer({a: calibration() for a in "NSEW"})

    def update(self, now, detections, **kw):
        defaults = dict(monotonic_now=now, captured_at=1000 + now, conflict_clear=False,
                        downstream_counts=dict.fromkeys("NSEW", 0),
                        downstream_capacity=dict.fromkeys("NSEW", 20),
                        sensors_healthy=True)
        defaults.update(kw)
        return self.producer.update(detections, **defaults)

    def test_stopped_vehicles_tally_by_class_and_person_is_not_a_vehicle(self):
        detections = [
            Detection(1, "N", 50, 130, "car"),
            Detection(2, "N", 60, 140, "car"),
            Detection(3, "N", 70, 150, "motorcycle"),
            Detection(4, "E", 50, 160, "bus"),
            Detection(5, "W", 50, 170, "person"),
        ]
        self.update(1, detections)   # first sighting: conservative speed, no tally
        data = self.update(1.1, detections)  # unchanged position: stopped
        classes = data["class_counts"]
        self.assertEqual(classes["N"], {"car": 2, "motorcycle": 1,
                                        "bicycle": 0, "bus": 0, "truck": 0})
        self.assertEqual(classes["E"]["bus"], 1)
        self.assertEqual(classes["W"], dict.fromkeys(VEHICLE_CLASSES, 0))
        self.assertEqual(data["counts"]["N"], 3)
        self.assertEqual(data["counts"]["E"], 1)
        self.assertEqual(data["counts"]["W"], 0)
        self.assertEqual(data["pedestrian_queue"]["W"], 1)

    def test_moving_vehicles_are_not_tallied_as_stopped(self):
        self.update(1, [Detection(1, "N", 50, 100, "car")])
        data = self.update(1.1, [Detection(1, "N", 50, 130, "car")])
        self.assertEqual(data["class_counts"]["N"]["car"], 0)
        self.assertEqual(data["counts"]["N"], 0)


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.client = CameraClient("http://127.0.0.1:1", "c" * 32,
                                   str(Path(self.directory.name) / "sender.db"))

    def tearDown(self):
        self.client.close()
        self.directory.cleanup()

    def traffic(self):
        traffic = dict.fromkeys(("downstream_counts", "approaching",
                                 "arrival_rate", "oldest_wait_s"),
                                dict.fromkeys("NSEW", 0))
        traffic["downstream_capacity"] = dict.fromkeys("NSEW", 100)
        return traffic

    def approach(self):
        return {"nearest_moving_distance_m": dict.fromkeys("NSEW", None),
                "max_approach_speed_mps": dict.fromkeys("NSEW", 0),
                "distance_uncertainty_m": dict.fromkeys("NSEW", 0)}

    def test_class_counts_require_v5_context(self):
        with self.assertRaises(ValueError):
            self.client.send(dict.fromkeys("NSEW", 0),
                             class_counts=breakdown())
        with self.assertRaises(ValueError):
            self.client.send(dict.fromkeys("NSEW", 0), traffic_state=self.traffic(),
                             class_counts=breakdown())

    def test_class_counts_validation_before_network(self):
        missing_approach = {a: dict.fromkeys(VEHICLE_CLASSES, 0) for a in "NSE"}
        person_vocabulary = {a: dict.fromkeys(
            ("car", "person", "bicycle", "bus", "truck"), 0) for a in "NSEW"}
        for bad in (missing_approach,               # approach W absent
                    person_vocabulary,              # person in vocabulary
                    breakdown(N={"car": 1.5}),      # non-whole
                    breakdown(N={"car": 501}),      # above cap
                    breakdown(N={"car": True})):    # bool
            with self.assertRaises(ValueError):
                self.client.send(dict.fromkeys("NSEW", 0),
                                 traffic_state=self.traffic(),
                                 approach_state=self.approach(),
                                 class_counts=bad)


class ServerRoundTripTests(HTTPTests):
    def test_v6_observation_accepted_and_journaled(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        client = CameraClient(f"http://127.0.0.1:{self.server.server_port}", "c" * 32,
                              str(Path(directory.name) / "sender.db"))
        self.addCleanup(client.close)
        result = client.send(
            dict.fromkeys("NSEW", 0),
            traffic_state=dict.fromkeys(
                        ("downstream_counts", "approaching",
                         "arrival_rate", "oldest_wait_s"), dict.fromkeys("NSEW", 0))
                    | {"downstream_capacity": dict.fromkeys("NSEW", 100)},
            approach_state={"nearest_moving_distance_m": dict.fromkeys("NSEW", None),
                            "max_approach_speed_mps": dict.fromkeys("NSEW", 0),
                            "distance_uncertainty_m": dict.fromkeys("NSEW", 0)},
            class_counts=breakdown(N={"car": 4, "bicycle": 1}))
        row = self.store.db.execute(
                    "SELECT payload FROM events WHERE kind='observation'").fetchone()
        journaled = json.loads(row[0])
        self.assertEqual(result["accepted_sequence"], journaled["sequence"])
        self.assertEqual(journaled["schema_version"], 6)
        classes = journaled["class_counts"]   # tuple order: N, S, E, W
        self.assertEqual(classes[0]["car"], 4)
        self.assertEqual(classes[0]["bicycle"], 1)
        self.assertEqual(classes[1]["car"], 0)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db_path = os.path.join(self.tmp.name, "edge.sqlite3")
        self.store = Store(self.db_path)
        self.addCleanup(self.store.close)

    def load(self):
        return report.load(self.db_path)

    def test_summarize_aggregates_class_totals_and_approach_matrix(self):
        self.store.event("observation", {
            "schema_version": 6, "sequence": 1, "captured_at": 100.0,
            "counts": [2, 1, 0, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 2, "motorcycle": 1},
                                      E={"truck": 1}),
        })
        self.store.event("observation", {
            "schema_version": 6, "sequence": 2, "captured_at": 101.0,
            "counts": [1, 0, 0, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 1}),
        })
        summary = report.summarize(self.load(), now=1000.0)
        self.assertEqual(summary["class_observations"], 2)
        self.assertEqual(summary["classes"]["car"]["vehicles"], 3)
        self.assertEqual(summary["classes"]["motorcycle"]["vehicles"], 1)
        self.assertEqual(summary["classes"]["truck"]["vehicles"], 1)
        self.assertEqual(summary["classes"]["bicycle"]["vehicles"], 0)
        self.assertEqual(summary["approach_classes"]["N"]["car"], 3)
        self.assertEqual(summary["approach_classes"]["E"]["truck"], 1)

    def test_summarize_without_class_fields_keeps_zero_buckets(self):
        self.store.event("observation", {
            "schema_version": 5, "sequence": 1, "captured_at": 100.0,
            "counts": [1, 1, 1, 1], "conflict_clear": True, "healthy": True,
        })
        summary = report.summarize(self.load(), now=1000.0)
        self.assertEqual(summary["class_observations"], 0)
        self.assertTrue(all(bucket["vehicles"] == 0
                            for bucket in summary["classes"].values()))

    def test_render_contains_class_table(self):
        self.store.event("observation", {
            "schema_version": 6, "sequence": 1, "captured_at": 100.0,
            "counts": [3, 0, 1, 0], "conflict_clear": True, "healthy": True,
            "class_counts": breakdown(N={"car": 3}, E={"bus": 1}),
        })
        text = report.render(report.summarize(self.load(), now=1000.0))
        self.assertIn("stopped vehicles by class", text)
        self.assertIn("obs with class data: 1", text)
        self.assertIn("car", text)
        self.assertIn("bus", text)

    def test_render_omits_class_table_for_old_journals(self):
        self.store.event("observation", {
            "schema_version": 5, "sequence": 1, "captured_at": 100.0,
            "counts": [1, 1, 1, 1], "conflict_clear": True, "healthy": True,
        })
        text = report.render(report.summarize(self.load(), now=1000.0))
        self.assertNotIn("stopped vehicles by class", text)


if __name__ == "__main__":
    unittest.main()