"""Transactional replay watermark and local audit journal (not tamper-proof)."""
import json
import sqlite3
import threading
import time
import os
from dataclasses import asdict


class InstanceLock:
    """OS lease released on process exit; never delete a live lock file."""
    def __init__(self, path):
        self.file = open(path, "a+b")
        if os.fstat(self.file.fileno()).st_size == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("another edge process owns this state directory") from None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.file.close()


class ReplayError(ValueError):
    pass


class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=.1)
        try:
            self._initialize()
        except BaseException:
            self.db.close()
            raise

    def _initialize(self):
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, sequence INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY, at REAL NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL
            );
        """)
        if "captured_at" not in {row[1] for row in self.db.execute("PRAGMA table_info(sources)")}:
            with self.db:
                self.db.execute("ALTER TABLE sources ADD COLUMN captured_at REAL NOT NULL DEFAULT -1")

    def accept(self, source, observation):
        with self.lock, self.db:
            row = self.db.execute("SELECT sequence,captured_at FROM sources WHERE id=?", (source,)).fetchone()
            if row and (observation.sequence <= row[0] or observation.captured_at < row[1]):
                raise ReplayError("sequence replayed or capture time regressed")
            self.db.execute("INSERT INTO sources(id,sequence,captured_at) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET sequence=excluded.sequence,captured_at=excluded.captured_at",
                            (source, observation.sequence, observation.captured_at))
            audit = dict(asdict(observation), source=source)
            # Metric detections are ephemeral; audit decisions, not trajectories.
            for field in ("nearest_moving_distance_m", "max_approach_speed_mps", "distance_uncertainty_m"):
                audit.pop(field, None)
            self._event("observation", audit)

    def _event(self, kind, payload):
        self.db.execute("INSERT INTO events(at,kind,payload) VALUES (?,?,?)",
                        (time.time(), kind, json.dumps(payload, allow_nan=False)))

    def event(self, kind, payload):
        with self.lock, self.db:
            self._event(kind, payload)

    def close(self):
        with self.lock:
            self.db.close()
