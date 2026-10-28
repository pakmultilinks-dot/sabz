import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import time
import unittest

from sabz_edge.core import APPROACHES, GROUPS, Timing
from sabz_edge.guard import CabinetAdapter, Guard
from sabz_edge.runtime import Runtime
from sabz_edge.store import Store
from process_support import spawn_module


FAST = Timing(min_green=.1, max_green=.8, yellow=.2, all_red=.1)


def command(seq, stage="ALL_RED", phase="NS", **kw):
    lamps = dict.fromkeys(APPROACHES, "RED")
    if stage != "ALL_RED":
        for a in GROUPS[phase]:
            lamps[a] = stage
    return dict(command_sequence=seq, stage=stage, phase=phase, lamps=lamps, lease_s=.5, **kw)


class GuardModelTests(unittest.TestCase):
    def test_local_clearance_and_lease_expiry(self):
        guard = Guard(FAST, 0)
        self.assertEqual(guard.accept(command(1, "GREEN"), .05)["stage"], "ALL_RED")
        self.assertEqual(guard.accept(command(2, "GREEN"), .1)["stage"], "GREEN")
        guard.advance(.61)
        self.assertEqual(guard.stage, "YELLOW")
        guard.advance(.80)
        self.assertEqual(guard.stage, "YELLOW")
        guard.advance(.82)
        self.assertEqual(guard.stage, "ALL_RED")
        result = guard.accept(command(3, "GREEN", "EW"), .83)
        self.assertEqual(result["stage"], "ALL_RED")
        self.assertEqual(result["fault"], "lease_expired")

    def test_direct_green_change_and_lamp_conflict_rejected(self):
        for invalid in (command(3, "GREEN", "EW"), dict(command(3), lamps=dict.fromkeys(APPROACHES, "GREEN"))):
            guard = Guard(FAST, 0)
            guard.accept(command(1), 0)
            guard.accept(command(2, "GREEN"), .1)
            out = guard.accept(invalid, .2)
            self.assertEqual(out["stage"], "YELLOW")
            self.assertIsNotNone(out["fault"])

    def test_local_minimum_and_maximum_green(self):
        guard = Guard(FAST, 0)
        guard.accept(command(1, "GREEN"), .1)
        self.assertEqual(guard.accept(command(2, "YELLOW"), .15)["stage"], "GREEN")
        for seq, now in enumerate((.3, .5, .7, .9), start=3):
            guard.accept(command(seq, "GREEN"), now)
        self.assertEqual(guard.stage, "YELLOW")

    def test_replay_does_not_renew_lease(self):
        guard = Guard(FAST, 0)
        guard.accept(command(5, "GREEN"), .1)
        out = guard.accept(command(5, "GREEN"), .2)
        self.assertEqual(out["fault"], "invalid_command")
        self.assertEqual(guard.deadline, .6)

    def test_randomized_hostile_proposals(self):
        rng = random.Random(93)
        for _ in range(100):
            guard = Guard(FAST, 0)
            now = 0
            for seq in range(1, 501):
                now += rng.random() * .15
                state = guard.accept(command(seq, rng.choice(["GREEN", "YELLOW", "ALL_RED"]), rng.choice(["NS", "EW"])), now)
                lamps = state["lamps"]
                self.assertFalse(any(lamps[a] != "RED" for a in "NS") and any(lamps[a] != "RED" for a in "EW"))
                if guard.fault:
                    self.assertNotEqual(state["stage"], "GREEN")


class GuardProcessTests(unittest.TestCase):
    def test_pipe_rejects_non_json_and_cannot_clear_fault(self):
        adapter = CabinetAdapter(FAST)
        try:
            for raw in (b"\x80\x04not-json", b'{"type":"command"}', b'[]',
                        b'{"type":"command","command":null}', b'[' * 1500 + b']' * 1500):
                adapter.pipe.send_bytes(raw)
                self.assertTrue(adapter.pipe.poll(1))
                reply = json.loads(adapter.pipe.recv_bytes(4096))
                self.assertEqual(reply["fault"], "invalid_command")
                self.assertEqual(reply["stage"], "ALL_RED")
                self.assertTrue(adapter.process.is_alive())
            with self.assertRaises(RuntimeError):
                adapter.apply(command(1, "GREEN"))
        finally:
            adapter.close()

    def test_cabinet_process_death_is_reported_as_unknown_output(self):
        runtime = Runtime(Store(":memory:"), FAST)
        runtime.adapter = CabinetAdapter(FAST)
        try:
            runtime.start()
            runtime.adapter.process.terminate()
            runtime.adapter.process.join(2)
            deadline = time.monotonic() + 1
            while runtime.last_error is None and time.monotonic() < deadline:
                time.sleep(.03)
            status = runtime.status()
            self.assertFalse(status["ready"])
            self.assertIsNone(status["cabinet_readback"])
            self.assertEqual(status["error"], "audit_or_adapter_failure")
        finally:
            runtime.close()

    def test_parent_stall_expires_lease_in_separate_process(self):
        adapter = CabinetAdapter(FAST)
        try:
            seq = 0
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                seq += 1
                adapter.apply(command(seq, "GREEN"))
                if adapter.readback["stage"] == "GREEN":
                    break
                time.sleep(.03)
            self.assertEqual(adapter.readback["stage"], "GREEN")
            time.sleep(.85)  # No output heartbeat: emulate a blocked edge process.
            actual = adapter.status()
            self.assertEqual(actual["stage"], "ALL_RED")
            self.assertEqual(actual["fault"], "lease_expired")
            with self.assertRaises(RuntimeError):
                adapter.apply(command(seq + 1, "GREEN", "EW"))
        finally:
            adapter.close()

    def test_killed_parent_still_clears_independent_cabinet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker, trace = root / "green.marker", root / "trace.jsonl"
            process = spawn_module("examples.guard_fault_worker", ["--marker", str(marker), "--trace", str(trace)])
            try:
                deadline = time.monotonic() + 8
                while not marker.exists() and time.monotonic() < deadline and process.poll() is None:
                    time.sleep(.04)
                self.assertTrue(marker.exists(), "isolated worker did not reach green")
                process.kill()
                process.wait(timeout=3)
                deadline = time.monotonic() + 4
                events = []
                while time.monotonic() < deadline:
                    events = [json.loads(line) for line in trace.read_text().splitlines() if line.endswith("}")]
                    if events and events[-1]["stage"] == "ALL_RED" and events[-1]["fault"]:
                        break
                    time.sleep(.04)
                self.assertTrue(any(event["stage"] == "GREEN" for event in events))
                self.assertTrue(any(event["stage"] == "YELLOW" and event["fault"] for event in events))
                self.assertEqual(events[-1]["stage"], "ALL_RED")
                self.assertIsNotNone(events[-1]["fault"])
            finally:
                if process.poll() is None:
                    process.kill(); process.wait(timeout=3)
                process.stderr.close()


if __name__ == "__main__":
    unittest.main()
