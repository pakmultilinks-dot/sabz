"""Independent-process, low-voltage bench cabinet emulator. No physical I/O.

It owns output timing, acknowledges actual emulated lamps and expires the
edge process's lease. IPC uses bounded JSON over an inherited local pipe,
never application pickle deserialization. This is software fault containment,
not a certified safety device or a separate host/privilege security boundary.
"""
import json
import multiprocessing
import threading
import time

from .core import Timing
from .cabinet_model import Guard

MAX_MESSAGE = 4096


def _send_message(pipe, message):
    raw = json.dumps(message, allow_nan=False).encode("utf-8")
    if len(raw) > MAX_MESSAGE:
        raise ValueError("cabinet message too large")
    pipe.send_bytes(raw)


def _receive_message(pipe):
    return json.loads(pipe.recv_bytes(MAX_MESSAGE).decode("utf-8"))



def _worker(pipe, timing, trace_path):
    guard = Guard(timing, time.monotonic())
    trace = open(trace_path, "a", encoding="utf-8", buffering=1) if trace_path else None
    previous = None
    disconnected = False
    stopping = False
    try:
        while True:
            if disconnected:
                time.sleep(.02)
            now = time.monotonic()
            guard.advance(now)
            if not disconnected and pipe.poll(.02):
                try:
                    message = _receive_message(pipe)
                    if not isinstance(message, dict) or message.get("type") not in ("command", "stop", "status"):
                        raise ValueError("invalid cabinet message")
                    now = time.monotonic()
                    if message["type"] == "command":
                        result = guard.accept(message["command"], now)
                    elif message["type"] == "stop":
                        guard.trip("edge_shutdown", now)
                        stopping = True
                        result = guard.snapshot(now)
                    else:  # Readback does not refresh the lease.
                        guard.advance(now)
                        result = guard.snapshot(now)
                    _send_message(pipe, result)
                except (ValueError, TypeError, UnicodeError, KeyError, RecursionError):
                    guard.trip("invalid_command", time.monotonic())
                    try:
                        _send_message(pipe, guard.snapshot(time.monotonic()))
                    except OSError:
                        disconnected = True
                except (EOFError, BrokenPipeError, OSError):
                    disconnected = True
                    guard.trip("edge_disconnected", time.monotonic())
            result = guard.snapshot(time.monotonic())
            signature = (result["stage"], result["phase"], result["fault"])
            if trace and signature != previous:
                trace.write(json.dumps(dict(result, monotonic=time.monotonic())) + "\n")
                trace.flush()
            previous = signature
            if (disconnected or stopping) and guard.stage == "ALL_RED":
                break
    finally:
        if trace:
            trace.close()
        pipe.close()


class CabinetAdapter:
    name = "independent-bench-cabinet"

    def __init__(self, timing=None, *, trace_path=None):
        self.timing = timing or Timing()
        context = multiprocessing.get_context("spawn")
        self.pipe, child = context.Pipe()
        self.lock = threading.Lock()
        self.process = context.Process(target=_worker, args=(child, self.timing, trace_path), name="sabz-bench-cabinet")
        self.process.start()
        child.close()
        self.last = None
        self.readback = None
        self.closed = False
        self.failed = False
        try:
            # Startup may import modules on Windows; complete before starting
            # the edge loop, then restart its timing epoch in Runtime.start().
            self._exchange({"type": "status"}, timeout=5)
        except Exception:
            self.pipe.close()
            self.process.terminate()
            self.process.join(2)
            raise

    def _exchange(self, message, timeout=.25):
        with self.lock:
            if self.closed or self.failed or not self.process.is_alive():
                raise RuntimeError("bench cabinet unavailable")
            _send_message(self.pipe, message)
            if not self.pipe.poll(timeout):
                self.failed = True
                raise RuntimeError("bench cabinet acknowledgement timeout")
            self.readback = _receive_message(self.pipe)
            return self.readback

    def apply(self, command):
        result = self._exchange({"type": "command", "command": command})
        if result["acknowledged_sequence"] != command["command_sequence"]:
            self.failed = True
            raise RuntimeError("bench cabinet acknowledgement mismatch")
        if result["fault"]:
            raise RuntimeError("bench cabinet fault")
        self.last = dict(command)

    def status(self):
        return self._exchange({"type": "status"})

    def close(self):
        if self.closed:
            return
        try:
            self._exchange({"type": "stop"})
        except (OSError, RuntimeError):
            pass
        self.closed = True
        self.pipe.close()
        # Let the independent process complete its own yellow clearance.
        self.process.join(self.timing.yellow + .8)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join(1)
