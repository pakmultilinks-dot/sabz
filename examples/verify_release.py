"""Real-time end-to-end bench evidence. Temporary listener/state; no hardware.

Run: python -m examples.verify_release --output validation/bench-run.json
"""
import argparse
import json
from pathlib import Path
import secrets
import tempfile
import threading
import time

from sabz_edge.client import CameraClient
from sabz_edge.runtime import Runtime
from sabz_edge.guard import CabinetAdapter
from sabz_edge.server import Server, Settings
from sabz_edge.store import Store


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="validation/bench-run.json")
    args = parser.parse_args()
    transitions = []
    samples = []
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        settings = Settings({"SABZ_CAMERA_TOKEN": secrets.token_urlsafe(32),
                             "SABZ_READER_TOKEN": secrets.token_urlsafe(32), "SABZ_PORT": "0"})
        store = Store(str(root / "edge.sqlite3"))
        runtime = Runtime(store)
        runtime.adapter = CabinetAdapter(trace_path=str(root / "cabinet.jsonl"))
        server = Server(settings, runtime)
        runtime.start()
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .05}, daemon=True)
        thread.start()
        client = CameraClient(f"http://127.0.0.1:{server.server_port}", settings.camera_token, str(root / "camera.sqlite3"))
        start = time.monotonic()
        signature = None
        try:
            while time.monotonic() - start < 25:
                elapsed = time.monotonic() - start
                sent_at = time.monotonic()
                if elapsed < 16:
                    client.send({"N": 0, "S": 0, "E": 20, "W": 10}, conflict_clear=True)
                status = runtime.status()
                elapsed = time.monotonic() - start
                state = status["last_output"]
                actual = status["cabinet_readback"]
                samples.append({"since_start_s": round(elapsed, 3), "cycle_latency_s": round(time.monotonic() - sent_at, 3),
                                "sensor_age_s": status["sensor_age_s"], "ready": status["ready"],
                                "stage": state["stage"], "reason": state["reason"]})
                current = (state["stage"], state["phase"], state["reason"])
                if current != signature:
                    transitions.append({**state, "since_start_s": round(elapsed, 3), "cabinet_readback": actual})
                    print(f"{elapsed:5.1f}s {state['stage']:7s} {state['phase']} {state['reason']}", flush=True)
                    signature = current
                time.sleep(.2)
            stages = [(x["stage"], x["phase"]) for x in transitions]
            passed = (("GREEN", "NS") in stages and ("GREEN", "EW") in stages
                      and any(x["stage"] == "YELLOW" and x["reason"] == "sensor_unavailable" for x in transitions)
                      and transitions[-1]["stage"] == "ALL_RED" and not runtime.status()["ready"])
            with store.lock:
                journal_count = store.db.execute("SELECT count(*) FROM events").fetchone()[0]
            cabinet_events = [json.loads(line) for line in (root / "cabinet.jsonl").read_text().splitlines()]
            passed = passed and cabinet_events[-1]["stage"] == "ALL_RED" and all(not event["fault"] for event in cabinet_events)
            passed = passed and all(sample["ready"] for sample in samples if 3 <= sample["since_start_s"] < 16)
            report = {"schema_version": 1, "mode": "bench", "input": "synthetic",
                      "time_basis": "real monotonic seconds", "physical_hardware": False,
                      "passed": passed, "journal_events": journal_count, "transitions": transitions,
                      "cabinet_events": cabinet_events, "samples": samples}
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            if not passed:
                raise SystemExit("bench release verification failed")
            print("PASS: startup, opposing demand, full clearance, sensor loss and all-red recovery", flush=True)
        finally:
            client.close()
            server.shutdown(); server.server_close(); thread.join(); runtime.close()


if __name__ == "__main__":
    main()
