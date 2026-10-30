"""Exploit / adversarial tests for the edge HTTP surface.

Covers: auth bypass attempts, framing attacks (duplicate Content-Length,
Transfer-Encoding smuggling), malformed JSON (duplicate keys, NaN),
schema fuzzing, replay, path traversal, and rate limiting.
"""
import http.client
import json
import socket
import threading
import unittest

from sabz_edge.runtime import Runtime
from sabz_edge.server import Limiter, Server, Settings
from sabz_edge.store import Store

import test_edge as fixtures


class SecurityTests(unittest.TestCase):
    """Fresh server per test, same fixture shape as fixtures.HTTPTests."""

    def setUp(self):
        self.store = Store(":memory:")
        self.runtime = Runtime(self.store)
        self.settings = Settings({"SABZ_CAMERA_TOKEN": "c" * 32,
                                  "SABZ_READER_TOKEN": "r" * 32,
                                  "SABZ_PORT": "0"})
        self.server = Server(self.settings, self.runtime)
        self.runtime.start()
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={"poll_interval": .01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.runtime.close()

    def request(self, method, path, data=None, token=None, headers=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=3)
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

    def raw(self, payload_bytes):
        """Send raw bytes; return (status_code, body_bytes)."""
        sock = socket.create_connection(
            ("127.0.0.1", self.server.server_port), timeout=3)
        try:
            sock.sendall(payload_bytes)
            sock.settimeout(3)
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        except socket.timeout:
            pass
        finally:
            sock.close()
        response = b"".join(chunks)
        head, _, body = response.partition(b"\r\n\r\n")
        status = int(head.split(b" ")[1])
        return status, body

    # --- authentication -------------------------------------------------
    def test_auth_bypass_attempts(self):
        camera, reader = "c" * 32, "r" * 32
        data = fixtures.payload()
        # Missing / wrong / role-mismatched tokens.
        self.assertEqual(self.request("POST", "/v1/observations", data)[0], 401)
        self.assertEqual(
            self.request("POST", "/v1/observations", data, "x" * 32)[0], 401)
        self.assertEqual(
            self.request("POST", "/v1/observations", data, reader)[0], 401)
        self.assertEqual(
            self.request("GET", "/v1/metrics", token=camera)[0], 401)
        self.assertEqual(
            self.request("POST", "/v1/preemption", {"approach": "N"},
                         camera)[0], 401)
        # Malformed scheme.
        for value in (camera, "Basic " + camera, "bearer " + camera,
                      "Bearer" + camera):
            self.assertEqual(
                self.request("GET", "/v1/status", token=None,
                             headers={"Authorization": value})[0], 401,
                msg=value)
        # Overlong token (> 263 chars incl. scheme) rejected before hashing.
        self.assertEqual(
            self.request("GET", "/v1/status", token=None,
                         headers={"Authorization": "Bearer " + "a" * 400})[0],
            401)

    def test_duplicate_authorization_headers_rejected(self):
        port = self.server.server_port
        raw = (b"GET /v1/status HTTP/1.1\r\n"
               b"Host: 127.0.0.1\r\n"
               b"Authorization: Bearer " + b"r" * 32 + b"\r\n"
               b"Authorization: Bearer " + b"c" * 32 + b"\r\n"
               b"Connection: close\r\n\r\n")
        status, _ = self.raw(raw)
        self.assertEqual(status, 401)

    # --- request framing ------------------------------------------------
    def test_duplicate_content_length_rejected(self):
        body = json.dumps(fixtures.payload()).encode()
        raw = (b"POST /v1/observations HTTP/1.1\r\n"
               b"Host: 127.0.0.1\r\n"
               b"Authorization: Bearer " + b"c" * 32 + b"\r\n"
               b"Content-Type: application/json\r\n"
               b"Content-Length: " + str(len(body)).encode() + b"\r\n"
               b"Content-Length: " + str(len(body)).encode() + b"\r\n"
               b"Connection: close\r\n\r\n" + body)
        status, _ = self.raw(raw)
        self.assertEqual(status, 400)

    def test_transfer_encoding_rejected(self):
        raw = (b"POST /v1/observations HTTP/1.1\r\n"
               b"Host: 127.0.0.1\r\n"
               b"Authorization: Bearer " + b"c" * 32 + b"\r\n"
               b"Content-Type: application/json\r\n"
               b"Transfer-Encoding: chunked\r\n"
               b"Connection: close\r\n\r\n"
               b"2\r\n{}\r\n0\r\n\r\n")
        status, _ = self.raw(raw)
        self.assertEqual(status, 400)

    def test_non_decimal_content_length_rejected(self):
        raw = (b"POST /v1/observations HTTP/1.1\r\n"
               b"Host: 127.0.0.1\r\n"
               b"Authorization: Bearer " + b"c" * 32 + b"\r\n"
               b"Content-Type: application/json\r\n"
               b"Content-Length: 12abc\r\n"
               b"Connection: close\r\n\r\n{}")
        status, _ = self.raw(raw)
        self.assertEqual(status, 400)

    # --- body limits and content type ----------------------------------
    def test_oversized_body_rejected(self):
        self.assertEqual(
            self.request("POST", "/v1/observations",
                         {"x": "a" * 5000}, "c" * 32)[0], 413)

    def test_wrong_content_type_rejected(self):
        self.assertEqual(
            self.request("POST", "/v1/observations", {}, "c" * 32,
                         {"Content-Type": "text/plain"})[0], 415)

    # --- malformed JSON -------------------------------------------------
    def test_malformed_json_rejected(self):
        camera = "c" * 32
        cases = [
            b"{",                                  # truncated
            b"not json at all",
            b'{"schema_version": 1, "schema_version": 1}',  # duplicate key
            b'{"counts": NaN}',                    # non-finite constant
            b'{"counts": Infinity}',
            b"[]",                                 # wrong top-level type
            b"null",
        ]
        for body in cases:
            raw = (b"POST /v1/observations HTTP/1.1\r\n"
                   b"Host: 127.0.0.1\r\n"
                   b"Authorization: Bearer " + camera.encode() + b"\r\n"
                   b"Content-Type: application/json\r\n"
                   b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                   b"Connection: close\r\n\r\n" + body)
            status, _ = self.raw(raw)
            self.assertEqual(status, 400, msg=body)

    # --- schema fuzzing -------------------------------------------------
    def test_observation_schema_fuzz(self):
        camera = "c" * 32
        import time
        stamp = time.time()
        base = {"schema_version": 3, "sequence": 1, "captured_at": stamp,
                "counts": dict.fromkeys("NSEW", 0),
                        "downstream_counts": dict.fromkeys("NSEW", 0),
                        "downstream_capacity": dict.fromkeys("NSEW", 10),
                        "approaching": dict.fromkeys("NSEW", 0),
                        "arrival_rate": dict.fromkeys("NSEW", 0),
                        "oldest_wait_s": dict.fromkeys("NSEW", 0),
                        "nearest_moving_distance_m": dict.fromkeys("NSEW", None),
                        "max_approach_speed_mps": dict.fromkeys("NSEW", 0),
                        "distance_uncertainty_m": dict.fromkeys("NSEW", 0),
                "conflict_clear": True, "healthy": True}
        bad = []
        # Wrong field set (missing key / extra key).
        missing = dict(base); missing.pop("arrival_rate"); bad.append(missing)
        extra = dict(base); extra["injected"] = 1; bad.append(extra)
        # Negative and out-of-range counts.
        negative = json.loads(json.dumps(base))
        negative["counts"]["N"] = -1; bad.append(negative)
        huge = json.loads(json.dumps(base))
        huge["counts"]["S"] = 501; bad.append(huge)
        # Bool-as-int and string types.
        boolseq = dict(base); boolseq["sequence"] = True; bad.append(boolseq)
        boolhealthy = dict(base); boolhealthy["healthy"] = 1
        bad.append(boolhealthy)
        strcount = json.loads(json.dumps(base))
        strcount["counts"]["E"] = "3"; bad.append(strcount)
        # Unknown schema version.
        version = dict(base); version["schema_version"] = 99
        bad.append(version)
        for body in bad:
            code, data = self.request("POST", "/v1/observations", body, camera)
            self.assertEqual(code, 400, msg=json.dumps(body)[:120])
            self.assertEqual(data, {"error": "invalid_observation"})

    # --- preemption -----------------------------------------------------
    def test_preemption_body_must_be_exact(self):
        reader = "r" * 32
        for body in ({}, {"approach": "X"}, {"approach": "N", "extra": 1},
                     {"approaches": "N"}, {"approach": 1},
                     {"approach": ["N"]}):
            code, data = self.request("POST", "/v1/preemption", body, reader)
            self.assertEqual(code, 400, msg=json.dumps(body))
            self.assertEqual(data, {"error": "invalid_observation"})

    # --- replay ---------------------------------------------------------
    def test_replay_returns_409(self):
        camera = "c" * 32
        data = fixtures.payload(stamp=__import__("time").time())
        self.assertEqual(
            self.request("POST", "/v1/observations", data, camera)[0], 202)
        code, body = self.request(
            "POST", "/v1/observations", dict(data), camera)
        self.assertEqual(code, 409)
        self.assertEqual(body, {"error": "sequence_replayed"})

    # --- routing --------------------------------------------------------
    def test_unknown_and_traversal_paths_404(self):
        camera = "c" * 32
        # http.client normalizes "//x" to "/x" before sending, so
        # scheme-relative tricks are covered by the raw-socket test below.
        for path in ("/admin", "/v1/../admin", "/v1/observations/../status",
                     "/.env", "/v1/observations/extra",
                     "/v1%2fstatus", "/favicon.ico"):
            self.assertEqual(self.request("GET", path, token=camera)[0], 404,
                             msg=path)
            self.assertEqual(
                self.request("POST", path, {}, camera)[0], 404, msg=path)

    def test_raw_scheme_relative_and_dotdot_paths_cannot_bypass(self):
        # No token: nothing here may return 200. Paths that normalize to
        # a real route are auth-gated (401); unknown ones 404.
        for path in (b"//v1/status",):
            status, _ = self.raw(
                b"GET " + path + b" HTTP/1.1\r\nHost: t\r\n"
                b"Connection: close\r\n\r\n")
            self.assertEqual(status, 401, path)
        for path in (b"/v1/../admin", b"/./healthz/../x", b"/admin",
                     b"/v1//status"):
            status, _ = self.raw(
                b"GET " + path + b" HTTP/1.1\r\nHost: t\r\n"
                b"Connection: close\r\n\r\n")
            self.assertEqual(status, 404, path)

    # --- rate limiting --------------------------------------------------
    def test_rate_limiter_blocks_flood(self):
        self.server.limiter = Limiter(rate=0, burst=1)
        self.assertEqual(self.request("GET", "/healthz")[0], 200)
        self.assertEqual(self.request("GET", "/healthz")[0], 429)
        self.assertEqual(self.request("GET", "/healthz")[0], 429)


if __name__ == "__main__":
    unittest.main()