"""Isolated service soak with real time, injected sensor faults and readback.

Synthetic bench only. No physical outputs. Default run takes 130 seconds.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

from sabz_edge.client import CameraClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=130)
    parser.add_argument("--output", default="validation/soak-run.json")
    args = parser.parse_args()
    if args.seconds < 125:
        parser.error("at least 125 seconds required to exercise the full scenario")
    samples = []
    # ignore_cleanup_errors: the hard terminate below can leave a process
    # holding edge.db for a moment on Windows; cleanup retries below first.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
        root = Path(directory)
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        camera, reader = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        env = dict(os.environ, SABZ_BIND="127.0.0.1", SABZ_PORT=str(port),
                   SABZ_CAMERA_TOKEN=camera, SABZ_READER_TOKEN=reader,
                   SABZ_STATE_PATH=str(root / "edge.db"))
        for key in ("SABZ_TLS_CERT", "SABZ_TLS_KEY", "SABZ_TIMING_FILE"):
            env.pop(key, None)
        process = subprocess.Popen([sys.executable, "-B", "-m", "sabz_edge.server"], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        client = None
        def get(path, authenticated=True):
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            try:
                connection.request("GET", path, headers={"Authorization": "Bearer " + reader} if authenticated else {})
                response = connection.getresponse()
                result = json.loads(response.read())
                if response.status != 200:
                    raise RuntimeError("unexpected service response")
                return result
            finally:
                connection.close()
        try:
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                try:
                    get("/healthz", False)
                    break
                except (OSError, RuntimeError, http.client.HTTPException):
                    if process.poll() is not None:
                        raise RuntimeError("isolated service exited during startup")
                    time.sleep(.05)
            else:
                raise RuntimeError("isolated service startup timeout")
            client = CameraClient(f"http://127.0.0.1:{port}", camera, str(root / "camera.db"))
            start = time.monotonic()
            previous = None
            while time.monotonic() - start < args.seconds:
                elapsed = time.monotonic() - start
                # Balanced demand exercises the local 60s maximum before faults.
                # Later: blocked clearance, unhealthy camera, then dropped feed.
                healthy = not 90 <= elapsed < 95
                clear = not 72 <= elapsed < 82
                if not 108 <= elapsed < 114:
                    client.send(dict.fromkeys("NSEW", 10), healthy=healthy, conflict_clear=clear)
                status = get("/v1/status")
                actual = status.get("cabinet_readback")
                if actual is None or status["error"] or status["controller"]["fault"] or actual["fault"]:
                    raise RuntimeError("unexpected control or cabinet fault")
                lamps = actual["lamps"]
                if any(lamps[a] != "RED" for a in "NS") and any(lamps[a] != "RED" for a in "EW"):
                    raise RuntimeError("conflicting emulated outputs")
                samples.append({"since_start_s": round(time.monotonic() - start, 3), "ready": status["ready"],
                                "sensor_age_s": status["sensor_age_s"], "requested": status["last_output"], "actual": actual})
                signature = (actual["stage"], actual["phase"], status["last_output"]["reason"])
                if signature != previous:
                    print(f"{elapsed:6.1f}s {actual['stage']:7s} {actual['phase']} {signature[2]}", flush=True)
                    previous = signature
                time.sleep(.25)
            passed = (any(sample["requested"]["reason"] == "maximum_green" for sample in samples)
                      and any(not sample["ready"] for sample in samples if 91 <= sample["since_start_s"] < 95)
                      and any(not sample["ready"] for sample in samples if 112 <= sample["since_start_s"] < 114)
                      and samples[-1]["ready"])
            report = {"schema_version": 1, "input": "synthetic", "physical_hardware": False,
                      "isolated_service_process": True, "duration_s": round(time.monotonic() - start, 3),
                      "passed": passed, "sample_count": len(samples), "samples": samples}
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            if not passed:
                raise RuntimeError("soak acceptance criteria not met")
            print("PASS: maximum green, sensor faults, feed loss, recovery, no conflicting readback", flush=True)
        finally:
            if client:
                client.close()
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=3)
            process.stderr.close()
            # terminate() does not cascade to the spawned cabinet child on
            # Windows; it exits on its own once the pipe breaks and the
            # controller reaches ALL_RED. Retry until it releases edge.db.
            deadline = time.monotonic() + 8
            while True:
                try:
                    shutil.rmtree(root)
                    break
                except PermissionError:
                    if time.monotonic() >= deadline:
                        raise
                    time.sleep(.05)


if __name__ == "__main__":
    main()
