import http.client
import io
import json
import time
import unittest
import urllib.error

from sabz_edge.core import Observation
from sabz_edge.dashboard import fetch, render, watch

import test_edge as fixtures


class MetricsEndpointTests(fixtures.HTTPTests):
    def test_metrics_requires_reader_token(self):
        self.assertEqual(self.request("GET", "/v1/metrics")[0], 401)
        self.assertEqual(self.request("GET", "/v1/metrics", token="c" * 32)[0], 401)
        code, data = self.request("GET", "/v1/metrics", token="r" * 32)
        self.assertEqual(code, 200)
        self.assertEqual(data["mode"], "bench")
        self.assertFalse(data["field_ready"])
        self.assertIn("controller", data)
        self.assertIn("metrics", data)
        self.assertIn("recent_transitions", data)

    def test_metrics_reflects_accepted_observation(self):
        stamp = time.time()
        zero = dict.fromkeys("NSEW", 0)
        data = {"schema_version": 5, "sequence": 7, "captured_at": stamp,
                "counts": {"N": 3, "S": 5, "E": 0, "W": 2},
                "conflict_clear": True, "healthy": True,
                "downstream_counts": dict(zero),
                "downstream_capacity": dict.fromkeys("NSEW", 1),
                "approaching": {"N": 1, "S": 2, "E": 0, "W": 4},
                "arrival_rate": {"N": 0.5, "S": 1.0, "E": 0.0, "W": 2.5},
                "oldest_wait_s": dict(zero),
                "nearest_moving_distance_m": dict.fromkeys("NSEW", None),
                "max_approach_speed_mps": dict(zero),
                "distance_uncertainty_m": dict(zero),
                "pedestrian_queue": dict(zero),
                "emergency": dict(zero)}
        self.runtime.submit("cam", Observation.parse(data, stamp))
        code, snapshot = self.request("GET", "/v1/metrics", token="r" * 32)
        self.assertEqual(code, 200)
        metrics = snapshot["metrics"]
        self.assertEqual(metrics["sequence"], 7)
        self.assertEqual(metrics["counts"], {"N": 3, "S": 5, "E": 0, "W": 2})
        self.assertEqual(metrics["approaching"], {"N": 1, "S": 2, "E": 0, "W": 4})
        self.assertEqual(metrics["arrival_rate"],
                         {"N": 0.5, "S": 1.0, "E": 0.0, "W": 2.5})
        self.assertTrue(metrics["healthy"])
        self.assertTrue(snapshot["sensor_fresh"])
        self.assertIsNotNone(snapshot["sensor_age_s"])
        self.assertLess(snapshot["sensor_age_s"], 3.0)

    def test_metrics_reports_recent_transitions(self):
        self.runtime.tick()
        self.runtime.tick()
        code, data = self.request("GET", "/v1/metrics", token="r" * 32)
        self.assertEqual(code, 200)
        transitions = data["recent_transitions"]
        self.assertTrue(transitions)
        self.assertLessEqual(len(transitions), 20)
        for event in transitions:
            self.assertEqual(event["kind"], "transition_intent")
            self.assertIn("stage", event["payload"])

    def test_root_page_lists_dashboard_routes(self):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("/v1/metrics", body)
            self.assertIn("/v1/telemetry", body)
        finally:
            connection.close()


class TelemetryEndpointTests(fixtures.HTTPTests):
    def test_telemetry_requires_camera_token(self):
        body = {"counts": dict.fromkeys("NSEW", 0),
                "conflict_clear": True, "healthy": True}
        self.assertEqual(self.request("POST", "/v1/telemetry", body)[0], 401)
        self.assertEqual(
            self.request("POST", "/v1/telemetry", body, "r" * 32)[0], 401)

    def test_telemetry_accepts_valid_feed_and_increments_sequence(self):
        body = {"counts": {"N": 4, "S": 1, "E": 0, "W": 9},
                "conflict_clear": True, "healthy": True}
        code, data = self.request("POST", "/v1/telemetry", body, "c" * 32)
        self.assertEqual(code, 202)
        self.assertEqual(data["accepted_sequence"], 0)
        code, data = self.request("POST", "/v1/telemetry", body, "c" * 32)
        self.assertEqual(code, 202)
        self.assertEqual(data["accepted_sequence"], 1)
        code, snapshot = self.request("GET", "/v1/metrics", token="r" * 32)
        self.assertEqual(code, 200)
        metrics = snapshot["metrics"]
        self.assertEqual(metrics["sequence"], 1)
        self.assertEqual(metrics["schema_version"], 1)
        self.assertEqual(metrics["counts"], {"N": 4, "S": 1, "E": 0, "W": 9})
        self.assertEqual(metrics["approaching"], {})
        self.assertEqual(metrics["arrival_rate"], {})
        self.assertTrue(snapshot["sensor_fresh"])

    def test_telemetry_rejects_malformed_bodies(self):
        camera = "c" * 32
        valid_counts = dict.fromkeys("NSEW", 0)
        bad_bodies = [
            {},
            {"counts": valid_counts, "conflict_clear": True},
            {"counts": valid_counts, "conflict_clear": True,
             "healthy": True, "extra": 1},
            {"counts": {"N": 0, "S": 0, "E": 0}, "conflict_clear": True,
             "healthy": True},
            {"counts": {"N": 0, "S": 0, "E": 0, "W": 0},
             "conflict_clear": "yes", "healthy": True},
            {"counts": valid_counts, "conflict_clear": True,
             "healthy": 1},
            {"counts": {"N": -1, "S": 0, "E": 0, "W": 0},
             "conflict_clear": True, "healthy": True},
        ]
        for body in bad_bodies:
            code, data = self.request("POST", "/v1/telemetry", body, camera)
            self.assertEqual(code, 400, msg=json.dumps(body))
            self.assertEqual(data, {"error": "invalid_observation"})


class DashboardRenderTests(unittest.TestCase):
    def snapshot(self, **overrides):
        base = {"mode": "bench", "field_ready": False, "now": 1000.0,
                "sensor_age_s": 0.4, "sensor_fresh": True,
                "loop_healthy": True, "last_error": None,
                "controller": {"stage": "GREEN", "phase": "NS", "elapsed_s": 2.5,
                               "lamps": {"N": "GREEN", "S": "GREEN", "E": "RED", "W": "RED"},
                               "reason": "min_green", "fault": None,
                               "algorithm": "fixed",
                               "preemption": {"active": False, "approach": None}},
                "metrics": {"sequence": 12, "schema_version": 5,
                            "healthy": True, "conflict_clear": True,
                            "counts": {"N": 3, "S": 5, "E": 0, "W": 2},
                            "approaching": {"N": 1, "S": 2, "E": 0, "W": 4},
                            "arrival_rate": {"N": 0.5, "S": 1.0, "E": 0.0, "W": 2.5},
                            "oldest_wait_s": {"N": 6, "S": 7, "E": 8, "W": 9},
                            "pedestrian_queue": {"N": 0, "S": 0, "E": 0, "W": 0}},
                "recent_transitions": [
                    {"at": 999.0, "kind": "transition_intent",
                     "payload": {"stage": "GREEN", "phase": "NS", "reason": "min_green"}}]}
        base.update(overrides)
        return base

    def test_render_shows_signal_health_counts_and_transitions(self):
        text = render(self.snapshot())
        self.assertIn("SABZ edge dashboard", text)
        self.assertIn("GREEN phase NS", text)
        self.assertIn("loop: healthy", text)
        self.assertIn("sensor: 0.4s fresh", text)
        self.assertIn("preemption: off", text)
        self.assertIn("seq 12", text)
        self.assertIn("N   GREEN", text)
        self.assertIn("E   RED", text)
        self.assertIn("recent transitions:", text)
        self.assertIn("min_green", text)

    def test_render_without_feed_and_with_stale_sensor(self):
        text = render(self.snapshot(metrics=None, sensor_age_s=None,
                                    sensor_fresh=False, loop_healthy=False,
                                    controller={"stage": "ALL_RED", "phase": "NS",
                                                "elapsed_s": 0.1, "lamps": {},
                                                "reason": "startup", "fault": None,
                                                "algorithm": "fixed",
                                                "preemption": {"active": True,
                                                               "approach": "E"}}))
        self.assertIn("no metric feed yet", text)
        self.assertIn("sensor: no feed STALE", text)
        self.assertIn("loop: DEGRADED", text)
        self.assertIn("preemption: ACTIVE E", text)

    def test_render_reports_errors_instead_of_crashing(self):
        self.assertIn("control_lock_busy",
                      render({"error": "control_lock_busy"}))
        self.assertIn("invalid_snapshot", render(None))
        self.assertIn("invalid_snapshot", render("nope"))


class DashboardClientTests(fixtures.HTTPTests):
    def test_fetch_reads_metrics_with_reader_token(self):
        url = f"http://127.0.0.1:{self.server.server_port}/v1/metrics"
        snapshot = fetch(url, "r" * 32)
        self.assertEqual(snapshot["mode"], "bench")
        with self.assertRaises(urllib.error.HTTPError) as caught:
            fetch(url, "c" * 32)
        self.assertEqual(caught.exception.code, 401)

    def test_watch_renders_one_frame(self):
        url = f"http://127.0.0.1:{self.server.server_port}/v1/metrics"
        out = io.StringIO()
        watch(url, "r" * 32, interval=0, out=out, max_frames=1)
        self.assertIn("SABZ edge dashboard", out.getvalue())
        self.assertIn("loop:", out.getvalue())


class DashboardCliTests(unittest.TestCase):
    def test_main_reads_installation_config(self):
        import contextlib
        import tempfile
        from pathlib import Path

        from sabz_edge.dashboard import main

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "instance.json"
            config.write_text(json.dumps(
                {"SABZ_PORT": "1", "SABZ_READER_TOKEN": "r" * 32,
                 "SABZ_TLS_CERT": ""}), encoding="utf-8")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main(["--directory", directory, "--frames", "1",
                      "--interval", "0"])
            self.assertIn("dashboard unavailable", out.getvalue())

    def test_main_reports_missing_config(self):
        import contextlib
        import tempfile

        from sabz_edge.dashboard import main

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SystemExit) as caught:
                main(["--directory", directory, "--frames", "1"])
            self.assertIn("cannot read", str(caught.exception))