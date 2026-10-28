import http.client
import json
from pathlib import Path
import random
import tempfile
import threading
import time
import unittest

from sabz_edge.core import Controller, Observation, Timing
from sabz_edge.runtime import Runtime
from sabz_edge.server import Limiter, Server, Settings, load_json
from sabz_edge.store import InstanceLock, ReplayError, Store
from sabz_edge.client import CameraClient


def payload(seq=1, stamp=1000, clear=True, healthy=True, counts=None):
    return {"schema_version": 1, "sequence": seq, "captured_at": stamp,
            "counts": counts or dict.fromkeys("NSEW", 0), "conflict_clear": clear, "healthy": healthy}


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.c = Controller(Timing(max_tick_gap=100), 0)

    def tick(self, now, **kw):
        obs = Observation.parse(payload(**kw), 1000)
        return self.c.tick(now, obs, now)

    def test_startup_and_minimum_green(self):
        self.assertEqual(self.tick(1)["stage"], "ALL_RED")
        self.assertEqual(self.tick(2)["stage"], "GREEN")
        self.assertEqual(self.tick(9, counts={"N": 0, "S": 0, "E": 30, "W": 0})["stage"], "GREEN")
        self.assertEqual(self.tick(10, counts={"N": 0, "S": 0, "E": 30, "W": 0})["stage"], "YELLOW")

    def test_maximum_green_and_clearance(self):
        self.tick(2)
        self.assertEqual(self.tick(62)["stage"], "YELLOW")
        self.assertEqual(self.tick(64.99)["stage"], "YELLOW")
        self.assertEqual(self.tick(65)["stage"], "ALL_RED")
        self.assertEqual(self.tick(66.99)["stage"], "ALL_RED")
        self.assertEqual(self.tick(67, clear=False)["stage"], "ALL_RED")
        out = self.tick(68)
        self.assertEqual(out["lamps"], {"N": "RED", "S": "RED", "E": "GREEN", "W": "GREEN"})

    def test_stale_sensor_terminates_through_yellow(self):
        self.tick(2)
        obs = Observation.parse(payload(), 1000)
        out = self.c.tick(6, obs, 2)
        self.assertEqual(out["stage"], "YELLOW")
        self.assertEqual(out["reason"], "sensor_unavailable")
        self.assertEqual(self.c.tick(9, obs, 2)["stage"], "ALL_RED")
        self.assertEqual(self.c.tick(50, obs, 2)["stage"], "ALL_RED")

    def test_delayed_tick_does_not_skip_clearance(self):
        self.tick(2)
        self.assertEqual(self.tick(80)["stage"], "YELLOW")
        self.assertEqual(self.tick(90)["stage"], "ALL_RED")
        self.assertEqual(self.tick(91)["stage"], "ALL_RED")

    def test_fault_latches_across_fresh_camera_packets(self):
        self.c = Controller(Timing(), 0)
        self.tick(2)
        self.assertEqual(self.c.fault, "control_loop_overrun")
        for now in (2.1, 2.2, 2.3):
            self.assertEqual(self.tick(now)["stage"], "ALL_RED")

    def test_request_frequency_cannot_accelerate_time(self):
        for _ in range(1000):
            self.assertEqual(self.tick(1)["stage"], "ALL_RED")

    def test_randomized_transition_invariants(self):
        rng = random.Random(42)
        self.c = Controller(Timing(max_tick_gap=100), 0)
        now = 0
        previous = self.c.snapshot(now)
        started = 0
        legal = {("ALL_RED", "GREEN"), ("GREEN", "YELLOW"), ("YELLOW", "ALL_RED")}
        for _ in range(20000):
            now += rng.random() * 0.8
            out = self.tick(now, clear=rng.random() > .2, healthy=rng.random() > .02,
                            counts={a: rng.randint(0, 50) for a in "NSEW"})
            lamps = out["lamps"]
            self.assertFalse(any(lamps[a] != "RED" for a in "NS") and any(lamps[a] != "RED" for a in "EW"))
            if previous["stage"] != out["stage"]:
                self.assertIn((previous["stage"], out["stage"]), legal)
                if previous["stage"] in ("YELLOW", "ALL_RED"):
                    minimum = 3 if previous["stage"] == "YELLOW" else 2
                    self.assertGreaterEqual(now - started, minimum)
                started = now
            previous = out


class ValidationTests(unittest.TestCase):
    def test_bad_numbers_types_and_shapes(self):
        for value in (float("nan"), float("inf"), -1, 101, True, "1", None):
            data = payload(); data["counts"]["N"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                Observation.parse(data, 1000)
        for key, value in (("sequence", True), ("sequence", -1), ("conflict_clear", 1), ("captured_at", 990), ("captured_at", 1002), ("schema_version", True)):
            data = payload(); data[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                Observation.parse(data, 1000)
        data = payload(); data["action"] = "GREEN"
        with self.assertRaises(ValueError):
            Observation.parse(data, 1000)

    def test_json_duplicates_and_nonfinite_rejected(self):
        for raw in ('{"a":1,"a":2}', '{"N":NaN}', '{"N":Infinity}'):
            with self.assertRaises(ValueError):
                load_json(raw)

    def test_unsafe_configuration_rejected(self):
        env = {"SABZ_CAMERA_TOKEN": "a" * 32, "SABZ_READER_TOKEN": "b" * 32}
        Settings(env)
        with self.assertRaises(ValueError):
            Settings(dict(env, SABZ_BIND="0.0.0.0"))
        with self.assertRaises(ValueError):
            Settings({})
        with self.assertRaises(ValueError):
            Settings(dict(env, SABZ_READER_TOKEN="a" * 32))
        for values in ({"yellow": float("nan")}, {"min_green": 70}, {"all_red": 0}):
            with self.assertRaises(ValueError):
                Timing(**values)


class RuntimeTests(unittest.TestCase):
    def test_only_one_owner_per_state_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "owner.lock")
            with InstanceLock(path):
                with self.assertRaises(RuntimeError):
                    InstanceLock(path)
            with InstanceLock(path):
                pass

    def test_replay_watermark_survives_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.sqlite3")
            obs = Observation.parse(payload(), 1000)
            store = Store(path); store.accept("camera", obs); store.close()
            store = Store(path)
            try:
                with self.assertRaises(ReplayError):
                    store.accept("camera", obs)
                store.accept("camera", Observation.parse(payload(seq=2), 1000))
                self.assertEqual(store.db.execute("SELECT count(*) FROM events").fetchone()[0], 2)
            finally:
                store.close()

    def test_observation_submission_does_not_advance_control(self):
        store = Store(":memory:")
        clock = Clock()
        runtime = Runtime(store, clock=clock, wall=lambda: 1000)
        try:
            for seq in range(500):
                runtime.submit("camera", Observation.parse(payload(seq=seq), 1000))
            self.assertEqual(runtime.controller.stage, "ALL_RED")
            clock.now = .5
            self.assertEqual(runtime.tick()["stage"], "ALL_RED")
        finally:
            runtime.close()

    def test_audit_failure_latches_and_prevents_green_output(self):
        store = Store(":memory:"); clock = Clock()
        runtime = Runtime(store, timing=Timing(max_tick_gap=100), clock=clock, wall=lambda: 1000)
        runtime.submit("camera", Observation.parse(payload(), 1000))
        runtime.tick()
        store.event = lambda *_: (_ for _ in ()).throw(OSError("disk full"))
        clock.now = 2
        with self.assertRaises(OSError):
            runtime.tick()
        self.assertEqual(runtime.adapter.last["stage"], "ALL_RED")
        self.assertFalse(runtime.status()["ready"])
        self.assertEqual(runtime.controller.fault, "audit_or_adapter_failure")
        runtime.close()


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.runtime = Runtime(self.store)
        self.settings = Settings({"SABZ_CAMERA_TOKEN": "c" * 32, "SABZ_READER_TOKEN": "r" * 32, "SABZ_PORT": "0"})
        self.server = Server(self.settings, self.runtime)
        self.runtime.start()
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.runtime.close()

    def request(self, method, path, data=None, token=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        head = {"Content-Type": "application/json"}
        if token:
            head["Authorization"] = "Bearer " + token
        head.update(headers or {})
        body = json.dumps(data) if data is not None else None
        connection.request(method, path, body, head)
        response = connection.getresponse()
        code, result = response.status, json.loads(response.read())
        connection.close()
        return code, result

    def test_root_explains_api_without_exposing_operational_status(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        try:
            connection.request("GET", "/")
            response = connection.getresponse()
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("text/html", response.getheader("Content-Type"))
            self.assertIn("default-src 'none'", response.getheader("Content-Security-Policy"))
            self.assertIn("signal outputs are emulated", body)
            self.assertNotIn(self.settings.reader_token, body)
            self.assertNotIn(self.settings.camera_token, body)
        finally:
            connection.close()
        self.assertEqual(self.request("GET", "/v1/status")[0], 401)

    def test_auth_roles_replay_and_old_routes(self):
        camera, reader = "c" * 32, "r" * 32
        self.assertEqual(self.request("GET", "/v1/status")[0], 401)
        self.assertEqual(self.request("GET", "/v1/status", token=camera)[0], 401)
        self.assertEqual(self.request("GET", "/readyz", token=reader)[0], 503)
        data = payload(stamp=time.time())
        self.assertEqual(self.request("POST", "/v1/observations", data, reader)[0], 401)
        self.assertEqual(self.request("POST", "/v1/observations", data, camera)[0], 202)
        self.assertEqual(self.request("POST", "/v1/observations", data, camera)[0], 409)
        status = self.request("GET", "/v1/status", token=reader)
        self.assertEqual(status[0], 200)
        self.assertFalse(status[1]["field_ready"])
        for path in ("/camera", "/feedback", "/v1/commands"):
            self.assertEqual(self.request("POST", path, {}, camera)[0], 404)

    def test_bad_payload_and_body_limit(self):
        camera = "c" * 32
        self.assertEqual(self.request("POST", "/v1/observations", payload(stamp=0), camera)[0], 400)
        self.assertEqual(self.request("POST", "/v1/observations", {"x": "a" * 5000}, camera)[0], 413)
        self.assertEqual(self.request("POST", "/v1/observations", {}, camera, {"Content-Type": "text/plain"})[0], 415)

    def test_rate_limiter(self):
        self.server.limiter = Limiter(rate=0, burst=1)
        self.assertEqual(self.request("GET", "/healthz")[0], 200)
        self.assertEqual(self.request("GET", "/healthz")[0], 429)

    def test_camera_sdk_and_persistent_sequence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "sender.sqlite3")
            endpoint = f"http://127.0.0.1:{self.server.server_port}"
            client = CameraClient(endpoint, "c" * 32, path)
            first = client.send(dict.fromkeys("NSEW", 1))["accepted_sequence"]
            client.close()
            client = CameraClient(endpoint, "c" * 32, path)
            try:
                second = client.send(dict.fromkeys("NSEW", 1))["accepted_sequence"]
                self.assertGreater(second, first)
            finally:
                client.close()

    def test_sdk_rejects_remote_plaintext_and_embedded_credentials(self):
        for endpoint in ("http://example.com", "https://user:pass@example.com", "https://example.com/?token=x"):
            with self.assertRaises(ValueError):
                CameraClient(endpoint, "c" * 32)


if __name__ == "__main__":
    unittest.main()
