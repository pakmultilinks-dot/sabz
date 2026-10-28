from concurrent.futures import ThreadPoolExecutor
import json
import socket
import time
import unittest
from unittest.mock import patch

from sabz_edge.client import CameraClient
from sabz_edge.server import Limiter
import test_edge as fixtures


class NetworkTests(unittest.TestCase):
    setUp = fixtures.HTTPTests.setUp
    tearDown = fixtures.HTTPTests.tearDown
    request = fixtures.HTTPTests.request

    def raw(self, headers, body=b""):
        with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=4) as sock:
            sock.sendall(headers + body)
            sock.shutdown(socket.SHUT_WR)
            data = b""
            while True:
                part = sock.recv(65536)
                if not part:
                    break
                data += part
        return int(data.split(b" ")[1])

    def test_ambiguous_framing_and_auth_rejected(self):
        base = b"POST /v1/observations HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nAuthorization: Bearer " + b"c" * 32 + b"\r\n"
        cases = [
            (b"Content-Length: 2\r\nContent-Length: 2\r\n", 400),
            (b"Transfer-Encoding: chunked\r\nContent-Length: 2\r\n", 400),
            (b"Content-Length: +2\r\n", 400),
            (b"Content-Length: -2\r\n", 400),
            (b"Content-Length: 9999999999999999999\r\n", 400),
            (b"Content-Length: 2\r\nAuthorization: Bearer " + b"c" * 32 + b"\r\n", 401),
        ]
        for headers, code in cases:
            with self.subTest(headers=headers[:40]):
                self.assertEqual(self.raw(base + headers + b"\r\n", b"{}"), code)

    def test_header_and_url_limits(self):
        self.assertEqual(self.raw(b"GET /healthz HTTP/1.0\r\nX-Large: " + b"a" * 17000 + b"\r\n\r\n"), 431)
        self.assertEqual(self.raw(b"GET /" + b"a" * 3000 + b" HTTP/1.0\r\n\r\n"), 414)

    def test_slow_header_has_absolute_deadline(self):
        started = time.monotonic()
        with socket.create_connection(("127.0.0.1", self.server.server_port), timeout=4) as sock:
            sock.sendall(b"GET /healthz HTTP/1.0\r\n")
            while time.monotonic() - started < 3.6:
                try:
                    sock.sendall(b"X-Slow: a\r\n")
                except OSError:
                    break
                time.sleep(.15)
            try:
                self.assertEqual(sock.recv(1), b"")
            except (ConnectionResetError, ConnectionAbortedError):
                pass
        self.assertLess(time.monotonic() - started, 4.2)
        self.assertTrue(self.runtime.thread.is_alive())

    def test_connection_saturation_does_not_stop_control_loop(self):
        sockets = []
        first_seq = self.runtime.output["command_sequence"]
        try:
            for _ in range(16):
                sock = socket.create_connection(("127.0.0.1", self.server.server_port), timeout=2)
                sock.sendall(b"GET /healthz HTTP/1.0\r\n")
                sockets.append(sock)
            time.sleep(.5)
            self.assertGreater(self.runtime.output["command_sequence"], first_seq + 2)
            self.assertIsNone(self.runtime.controller.fault)
        finally:
            for sock in sockets:
                sock.close()

    def test_unknown_routes_share_request_budget(self):
        self.server.limiter = Limiter(rate=0, burst=1)
        self.assertEqual(self.request("GET", "/not-a-route")[0], 404)
        self.assertEqual(self.request("GET", "/not-a-route")[0], 429)

    def test_early_post_errors_deliver_response_before_connection_close(self):
        self.server.limiter = Limiter(rate=10000, burst=10000)
        for _ in range(25):
            self.assertEqual(self.request("POST", "/camera", {}, "c" * 32)[0], 404)
            self.assertEqual(self.request("POST", "/v1/observations", {}, "r" * 32)[0], 401)
            self.assertEqual(self.request("POST", "/v1/observations", {"x": "a" * 5000}, "c" * 32)[0], 413)

    def test_concurrent_duplicate_observations_accept_exactly_once(self):
        self.server.limiter = Limiter(rate=10000, burst=10000)
        data = fixtures.payload(seq=77, stamp=time.time())
        with ThreadPoolExecutor(max_workers=8) as pool:
            codes = list(pool.map(lambda _: self.request("POST", "/v1/observations", data, "c" * 32)[0], range(32)))
        self.assertEqual(codes.count(202), 1)
        self.assertEqual(codes.count(409), 31)
        self.assertEqual(self.store.db.execute("SELECT count(*) FROM events WHERE kind='observation'").fetchone()[0], 1)

    def test_camera_does_not_use_environment_proxy(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"http_proxy": "http://127.0.0.1:1", "HTTP_PROXY": "http://127.0.0.1:1", "no_proxy": "", "NO_PROXY": ""}):
            client = CameraClient(f"http://127.0.0.1:{self.server.server_port}", "c" * 32, str(Path(directory) / "sender.db"))
            try:
                self.assertEqual(client.send(dict.fromkeys("NSEW", 0))["mode"], "bench")
            finally:
                client.close()

    def test_numeric_payload_fuzz_does_not_latch_service_fault(self):
        self.server.limiter = Limiter(rate=10000, burst=10000)
        for value in (True, None, "NaN", [], {}, -1, 101, 10**1000, 1e300):
            data = fixtures.payload(stamp=time.time())
            data["counts"]["N"] = value
            with self.subTest(type=type(value).__name__):
                self.assertEqual(self.request("POST", "/v1/observations", data, "c" * 32)[0], 400)
                self.assertIsNone(self.runtime.controller.fault)


if __name__ == "__main__":
    unittest.main()
