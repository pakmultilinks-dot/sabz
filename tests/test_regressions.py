"""Adversarial regressions found during the second integration review."""
import tempfile
from pathlib import Path
import unittest

from sabz_edge.core import Observation, Timing
from sabz_edge.runtime import Runtime
from sabz_edge.store import ReplayError, Store


def observation(seq=1, stamp=1000):
    return Observation.parse({"schema_version": 1, "sequence": seq, "captured_at": stamp,
                             "counts": dict.fromkeys("NSEW", 0), "conflict_clear": True, "healthy": True}, 1000)


class RegressionTests(unittest.TestCase):
    def test_large_json_integer_is_validation_error(self):
        data = {"schema_version": 1, "sequence": 1, "captured_at": 1000,
                "counts": {"N": 10**1000, "S": 0, "E": 0, "W": 0},
                "conflict_clear": True, "healthy": True}
        with self.assertRaises(ValueError):
            Observation.parse(data, 1000)

    def test_new_sequence_cannot_replace_with_older_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "state.db")
            store = Store(path)
            store.accept("camera", observation(1, 1000))
            store.close()
            store = Store(path)
            try:
                with self.assertRaises(ReplayError):
                    store.accept("camera", observation(2, 999))
            finally:
                store.close()

    def test_slow_audit_cannot_release_expired_green(self):
        now = [0.0]
        store = Store(":memory:")
        runtime = Runtime(store, Timing(stale_after=.3, max_tick_gap=10), clock=lambda: now[0], wall=lambda: 1000)
        runtime.tick()
        now[0] = 2
        runtime.submit("camera", observation())
        original = store.event
        def slow_event(*args):
            original(*args)
            now[0] += .8
        store.event = slow_event
        try:
            with self.assertRaises(RuntimeError):
                runtime.tick()
            self.assertEqual(runtime.adapter.last["stage"], "ALL_RED")
        finally:
            runtime.close()


if __name__ == "__main__":
    unittest.main()
