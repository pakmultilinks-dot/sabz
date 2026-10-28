from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest

from sabz_edge.core import Observation, Timing
from sabz_edge.guard import CabinetAdapter
from sabz_edge.runtime import Runtime
from sabz_edge.store import ReplayError, Store


def obs(seq=1):
    return Observation.parse({"schema_version": 1, "sequence": seq, "captured_at": time.time(),
                              "counts": dict.fromkeys("NSEW", 0), "conflict_clear": True, "healthy": True}, time.time())


class StorageFaultTests(unittest.TestCase):
    def test_sqlite_writer_contention_has_short_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "edge.db")
            store = Store(path)
            blocker = sqlite3.connect(path)
            blocker.execute("BEGIN IMMEDIATE")
            start = time.monotonic()
            try:
                with self.assertRaises(sqlite3.OperationalError):
                    store.accept("camera", obs())
                self.assertLess(time.monotonic() - start, .5)
            finally:
                blocker.rollback(); blocker.close()
            store.accept("camera", obs())
            self.assertEqual(store.db.execute("SELECT count(*) FROM events").fetchone()[0], 1)
            store.close()

    def test_disk_full_rolls_back_replay_watermark(self):
        store = Store(":memory:")
        original = store._event
        def disk_full(*_):
            raise sqlite3.OperationalError("database or disk is full")
        store._event = disk_full
        try:
            with self.assertRaises(sqlite3.OperationalError):
                store.accept("camera", obs())
            self.assertEqual(store.db.execute("SELECT count(*) FROM sources").fetchone()[0], 0)
            store._event = original
            store.accept("camera", obs())
        finally:
            store.close()

    def test_corrupt_database_refuses_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "corrupt.db"
            path.write_bytes(b"not a sqlite database")
            with self.assertRaises(sqlite3.DatabaseError):
                Store(str(path))

    def test_blocked_audit_cannot_block_independent_clearance(self):
        timing = Timing(min_green=.1, max_green=10, yellow=.2, all_red=.1)
        runtime = Runtime(Store(":memory:"), timing)
        runtime.adapter = CabinetAdapter(timing)
        release, entered = threading.Event(), threading.Event()
        original = runtime.store.event
        try:
            runtime.submit("camera", obs())
            runtime.start()
            deadline = time.monotonic() + 3
            while runtime.adapter.readback["stage"] != "GREEN" and time.monotonic() < deadline:
                time.sleep(.03)
            self.assertEqual(runtime.adapter.readback["stage"], "GREEN")
            def blocked_event(*args):
                entered.set()
                release.wait(3)
                original(*args)
            runtime.store.event = blocked_event
            with runtime.lock:
                runtime.controller.trip("injected_fault")
            self.assertTrue(entered.wait(1))
            started = time.monotonic()
            self.assertEqual(runtime.status()["error"], "control_lock_busy")
            self.assertLess(time.monotonic() - started, .3)
            time.sleep(.8)
            actual = runtime.adapter.status()
            self.assertEqual(actual["stage"], "ALL_RED")
            self.assertEqual(actual["fault"], "lease_expired")
        finally:
            release.set()
            runtime.close()


if __name__ == "__main__":
    unittest.main()
