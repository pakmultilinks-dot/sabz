"""Tests for the historical report tool."""
import json
import os
import tempfile
import unittest

from sabz_edge import report
from sabz_edge.store import Store


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = os.path.join(self.tmp.name, "edge.sqlite3")
        self.store = Store(self.db)
        self.addCleanup(self.store.close)

    def seed(self):
        self.store.event("observation", {
            "schema_version": 5, "sequence": 1, "captured_at": 100.0,
            "counts": [20.0, 10.0, 1.0, 1.0], "conflict_clear": True,
            "healthy": True, "oldest_wait_s": 42.5, "pedestrian_queue": 3,
        })
        self.store.event("observation", {
            "schema_version": 5, "sequence": 2, "captured_at": 101.0,
            "counts": {"N": 4, "S": 6, "E": 0, "W": 2},
            "conflict_clear": True, "healthy": True,
        })
        self.store.event("transition_intent", {"stage": "GREEN", "phase": "NS",
                                               "reason": "green_elapsed"})
        self.store.event("transition_intent", {"stage": "YELLOW", "phase": "NS",
                                               "reason": "yellow_elapsed"})
        self.store.event("preemption_requested", {"approach": "N"})

    def test_load_returns_events_oldest_first(self):
        self.seed()
        events = report.load(self.db)
        self.assertEqual(len(events), 5)
        self.assertEqual([kind for _, kind, _ in events],
                         ["observation", "observation", "transition_intent",
                          "transition_intent", "preemption_requested"])
        self.assertTrue(all(isinstance(data, dict) for _, _, data in events))

    def test_load_since_filters_old_events(self):
            self.seed()
            self.assertEqual(len(report.load(self.db, since=0)), 5)
            self.assertEqual(report.load(self.db, since=10**12), [])

    def test_summarize_counts_list_and_dict_counts(self):
        self.seed()
        summary = report.summarize(report.load(self.db), now=1000.0)
        self.assertEqual(summary["totals"]["observations"], 2)
        self.assertEqual(summary["approaches"]["N"]["vehicles"], 24)
        self.assertEqual(summary["approaches"]["S"]["vehicles"], 16)
        self.assertEqual(summary["approaches"]["E"]["vehicles"], 1)
        self.assertEqual(summary["approaches"]["W"]["vehicles"], 3)
        self.assertEqual(summary["approaches"]["N"]["avg_vehicles"], 12.0)
        self.assertEqual(summary["approaches"]["N"]["observations"], 2)

    def test_summarize_wait_pedestrian_and_preemption(self):
        self.seed()
        summary = report.summarize(report.load(self.db), now=1000.0)
        self.assertEqual(summary["max_wait_s"], 42.5)
        self.assertEqual(summary["max_pedestrian_queue"], 3)
        self.assertEqual(summary["totals"]["preemptions"], 1)
        self.assertEqual(summary["approaches"]["N"]["preemptions"], 1)
        self.assertEqual(summary["approaches"]["S"]["preemptions"], 0)

    def test_summarize_transitions_and_dwell(self):
        self.seed()
        summary = report.summarize(report.load(self.db), now=1000.0)
        self.assertEqual(summary["totals"]["transitions"], 2)
        self.assertEqual(summary["transition_reasons"],
                         {"green_elapsed": 1, "yellow_elapsed": 1})
        # dwell attributed to the stage of the *previous* transition
        self.assertAlmostEqual(sum(summary["stage_dwell_s"].values()), 0.0, delta=1)

    def test_summarize_empty_window(self):
        summary = report.summarize([], now=500.0)
        self.assertIsNone(summary["window"]["first_at"])
        self.assertEqual(summary["totals"]["observations"], 0)
        self.assertEqual(summary["max_wait_s"], None)

    def test_summarize_skips_corrupt_payloads(self):
        self.store.db.execute(
            "INSERT INTO events(at,kind,payload) VALUES (?,?,?)",
            (1.0, "observation", "{not json"))
        self.store.db.commit()
        summary = report.summarize(report.load(self.db), now=500.0)
        self.assertEqual(summary["totals"]["observations"], 0)

    def test_render_contains_key_lines(self):
        self.seed()
        text = report.render(report.summarize(report.load(self.db), now=1000.0))
        self.assertIn("SABZ historical report", text)
        self.assertIn("2 observations, 2 transitions, 1 preemptions", text)
        self.assertIn("max wait: 42.5s", text)
        self.assertIn("green_elapsed: 1", text)
        self.assertIn("24.0", text)
        self.assertIn("12.0", text)

    def test_render_empty_window(self):
        text = report.render(report.summarize([], now=500.0))
        self.assertEqual(text, "SABZ report: no events recorded in this window.")

    def test_parse_since_durations(self):
        self.assertIsNone(report.parse_since("all"))
        self.assertIsNone(report.parse_since(None))
        now = report.time.time()
        self.assertAlmostEqual(report.parse_since("90s"), now - 90, delta=3)
        self.assertAlmostEqual(report.parse_since("30m"), now - 1800, delta=3)
        self.assertAlmostEqual(report.parse_since("24h"), now - 86400, delta=3)
        self.assertAlmostEqual(report.parse_since("7d"), now - 604800, delta=3)

    def test_summarize_pedestrian_flow_per_approach(self):
        self.store.event("observation", {
            "schema_version": 5, "sequence": 1, "captured_at": 100.0,
            "counts": [1, 1, 1, 1], "conflict_clear": True, "healthy": True,
            "pedestrian_queue": [3, 1, 0, 2],
        })
        self.store.event("observation", {
            "schema_version": 5, "sequence": 2, "captured_at": 101.0,
            "counts": [1, 1, 1, 1], "conflict_clear": True, "healthy": True,
            "pedestrian_queue": [1, 5, 0, 0],
        })
        summary = report.summarize(report.load(self.db), now=1000.0)
        n = summary["pedestrians"]["N"]
        self.assertEqual((n["observations"], n["pedestrians"], n["max_pedestrians"]),
                         (2, 4, 3))
        self.assertEqual(n["avg_pedestrians"], 2.0)
        self.assertEqual(summary["pedestrians"]["S"]["pedestrians"], 6)
        self.assertEqual(summary["pedestrians"]["E"]["pedestrians"], 0)
        self.assertEqual(summary["pedestrians"]["W"]["pedestrians"], 2)
        self.assertEqual(summary["max_pedestrian_queue"], 5)

    def test_scalar_pedestrian_payload_keeps_flow_buckets_empty(self):
        self.seed()  # seeds a scalar pedestrian_queue: 3
        summary = report.summarize(report.load(self.db), now=1000.0)
        self.assertEqual(summary["max_pedestrian_queue"], 3)
        self.assertTrue(all(bucket["observations"] == 0
                            for bucket in summary["pedestrians"].values()))

    def test_peak_hour_foot_traffic_picks_densest_window(self):
        def insert(at, peds):
            self.store.db.execute(
                "INSERT INTO events(at,kind,payload) VALUES (?,?,?)",
                (at, "observation", json.dumps(
                    {"counts": [0, 0, 0, 0], "pedestrian_queue": peds})))
        insert(100.0, [2, 3, 0, 0])    # total 5
        insert(1000.0, [7, 0, 0, 0])   # total 7
        insert(4000.0, [4, 0, 0, 0])   # total 4, outside 1h of the first
        self.store.db.commit()
        summary = report.summarize(report.load(self.db), now=5000.0)
        # Densest rolling hour is [100, 1000] with 12 pedestrians; the slice
        # ending at 4000 drops the t=100 observation and only totals 11.
        self.assertEqual(summary["peak_hour"],
                         {"first_at": 100.0, "last_at": 1000.0, "pedestrians": 12})

    def test_render_contains_pedestrian_flow_lines(self):
        self.store.event("observation", {
            "schema_version": 5, "sequence": 1, "captured_at": 100.0,
            "counts": [1, 1, 1, 1], "conflict_clear": True, "healthy": True,
            "pedestrian_queue": [3, 1, 0, 2],
        })
        text = report.render(report.summarize(report.load(self.db), now=1000.0))
        self.assertIn("peds  avg/obs  max", text)
        self.assertIn("peak hour foot traffic: 6 peds", text)

    def test_main_json_output(self):
        self.seed()
        import io
        from contextlib import redirect_stdout
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = report.main(["--database", self.db, "--json"])
        self.assertEqual(code, 0)
        data = json.loads(buffer.getvalue())
        self.assertEqual(data["totals"]["observations"], 2)

    def test_main_text_output(self):
        self.seed()
        import io
        from contextlib import redirect_stdout
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = report.main(["--database", self.db])
        self.assertEqual(code, 0)
        self.assertIn("SABZ historical report", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()