import http.client
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from process_support import spawn_module


class ServiceProcessTests(unittest.TestCase):
    def test_kill_restart_replay_protection_and_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            timing_path = root / "timing.json"
            timing_path.write_text(json.dumps({"min_green": .1, "max_green": 10, "yellow": .2, "all_red": .1}))
            with socket.socket() as reservation:
                reservation.bind(("127.0.0.1", 0))
                port = reservation.getsockname()[1]
            camera, reader = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            env = dict(os.environ, SABZ_BIND="127.0.0.1", SABZ_PORT=str(port),
                       SABZ_CAMERA_TOKEN=camera, SABZ_READER_TOKEN=reader,
                       SABZ_STATE_PATH=str(root / "edge.db"), SABZ_TIMING_FILE=str(timing_path))
            env.pop("SABZ_TLS_CERT", None); env.pop("SABZ_TLS_KEY", None)

            def request(method, path, token=None, body=None):
                client = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                headers = {"Content-Type": "application/json"}
                if token:
                    headers["Authorization"] = "Bearer " + token
                try:
                    client.request(method, path, json.dumps(body) if body else None, headers)
                    response = client.getresponse()
                    return response.status, json.loads(response.read())
                finally:
                    client.close()

            def start():
                process = spawn_module("sabz_edge.server", env=env)
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline and process.poll() is None:
                    try:
                        if request("GET", "/healthz")[0] == 200:
                            return process
                    except (OSError, http.client.HTTPException):
                        pass
                    time.sleep(.05)
                process.kill(); process.wait(timeout=3)
                process.stderr.close()
                self.fail("isolated edge service did not start")

            def stop(process):
                if process.poll() is None:
                    process.kill(); process.wait(timeout=3)
                process.stderr.close()

            process = start()
            body = {"schema_version": 1, "sequence": 500, "captured_at": time.time(),
                    "counts": dict.fromkeys("NSEW", 0), "healthy": True, "conflict_clear": True}
            try:
                self.assertEqual(request("POST", "/v1/observations", camera, body)[0], 202)
                deadline = time.monotonic() + 2
                state = None
                while time.monotonic() < deadline:
                    _, state = request("GET", "/v1/status", reader)
                    if state["cabinet_readback"]["stage"] == "GREEN":
                        break
                    time.sleep(.05)
                self.assertEqual(state["cabinet_readback"]["stage"], "GREEN")
                self.assertFalse(state["field_ready"])
            finally:
                stop(process)
            process = start()
            try:
                state = request("GET", "/v1/status", reader)[1]
                self.assertEqual(state["cabinet_readback"]["stage"], "ALL_RED")
                self.assertFalse(state["ready"])
                body["captured_at"] = time.time()
                self.assertEqual(request("POST", "/v1/observations", camera, body)[0], 409)
                body["sequence"] = 501
                self.assertEqual(request("POST", "/v1/observations", camera, body)[0], 202)
            finally:
                stop(process)


if __name__ == "__main__":
    unittest.main()
