"""Edge-triggered alert journaling: fault, preemption, sensor edges, local alert log."""
import json
import tempfile
import unittest
from pathlib import Path

import test_edge as fixtures
from sabz_edge.core import Observation, Timing
from sabz_edge.runtime import Runtime
from sabz_edge.store import Store


def observation(seq=1, stamp=1000):
    return Observation.parse(
        {"schema_version": 1, "sequence": seq, "captured_at": stamp,
         "counts": dict.fromkeys("NSEW", 0), "conflict_clear": True, "healthy": True},
        1000)


def alert_rows(store):
    rows = store.db.execute(
        "SELECT payload FROM events WHERE kind='alert' ORDER BY at, rowid").fetchall()
    return [json.loads(row[0]) for row in rows]


class AlertJournalTests(unittest.TestCase):
    def test_fault_latch_alerts_once_until_cleared(self):
        store = Store(":memory:")
        clock = fixtures.Clock()
        runtime = Runtime(store, clock=clock, wall=lambda: 1000)
        try:
            runtime.submit("camera", observation())
            clock.now = 1
            runtime.tick()
            self.assertEqual(alert_rows(store), [])
            with runtime.lock:
                runtime.controller.trip("injected_fault")
            runtime.tick()
            runtime.tick()
            rows = alert_rows(store)
            self.assertEqual([r["kind"] for r in rows], ["fault_latched"])
            self.assertEqual(rows[0]["fault"], "injected_fault")
        finally:
            runtime.close()

    def test_preemption_request_alerts_and_appears_in_metrics(self):
        store = Store(":memory:")
        clock = fixtures.Clock()
        runtime = Runtime(store, clock=clock, wall=lambda: 1000)
        try:
            runtime.preempt("E")
            rows = alert_rows(store)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["kind"], "preemption_requested")
            self.assertEqual(rows[0]["approach"], "E")
            snapshot = runtime.metrics_snapshot()
            self.assertIn("recent_alerts", snapshot)
            self.assertEqual(snapshot["recent_alerts"][0]["payload"]["kind"],
                             "preemption_requested")
        finally:
            runtime.close()

    def test_sensor_loss_and_recovery_alert_on_edges_only(self):
        now = [0.0]
        store = Store(":memory:")
        runtime = Runtime(store, Timing(stale_after=3.0, max_tick_gap=10),
                          clock=lambda: now[0], wall=lambda: 1000)
        try:
            runtime.submit("camera", observation())
            runtime.tick()                      # fresh; edge baseline, no alert
            now[0] = 1
            runtime.tick()                      # still fresh
            self.assertEqual(alert_rows(store), [])
            now[0] = 5                          # age 5 > stale_after 3
            runtime.tick()
            runtime.tick()                      # still stale: no duplicate
            rows = alert_rows(store)
            self.assertEqual([r["kind"] for r in rows], ["sensor_lost"])
            self.assertEqual(rows[0]["age_s"], 5)
            now[0] = 6
            runtime.submit("camera", observation(seq=2))
            runtime.tick()                      # fresh again
            rows = alert_rows(store)
            self.assertEqual([r["kind"] for r in rows],
                             ["sensor_lost", "sensor_recovered"])
        finally:
            runtime.close()

    def test_audit_failure_alerts_even_when_transition_journal_fails(self):
        store = Store(":memory:")
        clock = fixtures.Clock()
        runtime = Runtime(store, timing=Timing(max_tick_gap=100),
                          clock=clock, wall=lambda: 1000)
        try:
            runtime.submit("camera", observation())
            original = store.event

            def failing(kind, payload):
                if kind == "transition_intent":
                    raise OSError("disk full")
                return original(kind, payload)

            store.event = failing
            clock.now = 1
            with self.assertRaises(OSError):
                runtime.tick()
            rows = alert_rows(store)
            self.assertEqual([r["kind"] for r in rows], ["audit_failure"])
            self.assertEqual(rows[0]["error"], "audit_or_adapter_failure")
            self.assertEqual(runtime.controller.fault, "audit_or_adapter_failure")
        finally:
            runtime.close()

    def test_local_alert_log_mirrors_journal(self):
        store = Store(":memory:")
        clock = fixtures.Clock()
        runtime = Runtime(store, clock=clock, wall=lambda: 1000)
        try:
            with tempfile.TemporaryDirectory() as directory:
                log_path = Path(directory) / "alerts.jsonl"
                runtime.set_alert_log(str(log_path))
                runtime.preempt("N")
                lines = log_path.read_text(encoding="utf-8").splitlines()
                self.assertEqual(len(lines), 1)
                record = json.loads(lines[0])
                self.assertEqual(record["kind"], "preemption_requested")
                self.assertEqual(record["approach"], "N")
        finally:
            runtime.close()

    def test_alert_log_failure_does_not_break_journaling(self):
        store = Store(":memory:")
        clock = fixtures.Clock()
        runtime = Runtime(store, clock=clock, wall=lambda: 1000)
        try:
            runtime.set_alert_log("\\\\nonexistent-dir\\\\alerts.jsonl")
            runtime.preempt("S")
            self.assertEqual([r["kind"] for r in alert_rows(store)],
                             ["preemption_requested"])
        finally:
            runtime.close()


class AlertDashboardTests(fixtures.HTTPTests):
    def test_metrics_endpoint_reports_recent_alerts(self):
        self.runtime.preempt("W")
        code, data = self.request("GET", "/v1/metrics",
                                  token=self.settings.reader_token)
        self.assertEqual(code, 200)
        self.assertIn("recent_alerts", data)
        self.assertEqual(data["recent_alerts"][0]["payload"]["kind"],
                         "preemption_requested")

    def test_render_shows_alerts_section(self):
        from sabz_edge.dashboard import render
        snapshot = self.runtime.metrics_snapshot()
        snapshot["recent_alerts"] = [
            {"at": 1000.0, "kind": "alert",
             "payload": {"kind": "sensor_lost", "age_s": 4.5}}]
        text = render(snapshot)
        self.assertIn("alerts:", text)
        self.assertIn("sensor_lost", text)
        self.assertIn("age_s=4.5", text)

    def test_render_omits_alerts_section_when_empty(self):
        from sabz_edge.dashboard import render
        text = render(self.runtime.metrics_snapshot())
        self.assertNotIn("alerts:", text)


if __name__ == "__main__":
    unittest.main()