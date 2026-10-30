"""Camera/telemetry SDK with durable sender sequence and verified TLS."""
import ipaddress
import json
from pathlib import Path
import sqlite3
import ssl
import time
import urllib.request
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward credentials to a redirect target.


class CameraClient:
    def __init__(self, endpoint, token, state_path="data/camera.sqlite3", *, ca_file=None):
        url = urlsplit(endpoint)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("endpoint must be an HTTP(S) origin without credentials")
        if url.scheme == "http":
            try:
                local = ipaddress.ip_address(url.hostname).is_loopback
            except ValueError:
                local = False
            if not local:
                raise ValueError("remote camera connection requires HTTPS")
        if not token or not token.isascii() or any(c.isspace() for c in token):
            raise ValueError("invalid camera token")
        context = ssl.create_default_context(cafile=ca_file)
        self.endpoint, self.token = endpoint.rstrip("/"), token
        self.last_timings = None
        Path(state_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(state_path, timeout=.1)
        try:
            # Avoid creating a rollback-journal file on every sensor frame.
            # FULL durability is retained; lock contention fails promptly.
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute("CREATE TABLE IF NOT EXISTS sequence (id INTEGER PRIMARY KEY CHECK(id=1), value INTEGER NOT NULL)")
            self.db.commit()
        except Exception:
            self.db.close()
            raise
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), NoRedirect,
            urllib.request.HTTPSHandler(context=context))

    def _next_sequence(self):
        # Reserve before sending. A lost response leaves a harmless gap.
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            row = self.db.execute("SELECT value FROM sequence WHERE id=1").fetchone()
            value = max(time.time_ns(), row[0] + 1 if row else 0)
            self.db.execute("INSERT INTO sequence VALUES (1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value", (value,))
        return value

    def send(self, counts, *, conflict_clear=False, healthy=True, captured_at=None, traffic_state=None,
                 approach_state=None, pedestrian_queue=None, emergency=None, class_counts=None):
        self.last_timings = None
        started = time.perf_counter()
        sequence = self._next_sequence()
        reserved = time.perf_counter()
        observation = {"schema_version": 1, "sequence": sequence,
                       "captured_at": time.time() if captured_at is None else captured_at,
                       "counts": counts, "conflict_clear": conflict_clear, "healthy": healthy}
        if class_counts is not None:
            # Schema v6 carries the full v1-v5 field set; absent pedestrian
            # demand and preemption requests are honestly reported as zero.
            if traffic_state is None or approach_state is None:
                raise ValueError("class_counts requires traffic_state and approach_state")
            if pedestrian_queue is None:
                pedestrian_queue = dict.fromkeys(("N", "S", "E", "W"), 0)
            if emergency is None:
                emergency = dict.fromkeys(("N", "S", "E", "W"), 0)
        if traffic_state is not None:
            fields = {"downstream_counts", "downstream_capacity", "approaching", "arrival_rate", "oldest_wait_s"}
            if not isinstance(traffic_state, dict) or set(traffic_state) != fields:
                raise ValueError("traffic_state must contain all observation v2 traffic fields")
            observation.update(traffic_state)
            observation["schema_version"] = 2
        if approach_state is not None:
            fields = {"nearest_moving_distance_m", "max_approach_speed_mps", "distance_uncertainty_m"}
            if traffic_state is None or not isinstance(approach_state, dict) or set(approach_state) != fields:
                raise ValueError("approach_state requires all metric fields and traffic_state")
            observation.update(approach_state)
            observation["schema_version"] = 3
            if pedestrian_queue is not None:
                fields = {"N", "S", "E", "W"}
                if traffic_state is None or approach_state is None:
                    raise ValueError("pedestrian_queue requires traffic_state and approach_state")
                if not isinstance(pedestrian_queue, dict) or set(pedestrian_queue) != fields:
                    raise ValueError("pedestrian_queue must contain all observation v4 pedestrian fields")
                for approach in fields:
                    value = pedestrian_queue[approach]
                    if (isinstance(value, bool) or not isinstance(value, (int, float))
                            or not 0 <= value <= 500 or int(value) != value):
                        raise ValueError("pedestrian_queue values must be whole numbers in 0..500")
                observation["pedestrian_queue"] = pedestrian_queue
                observation["schema_version"] = 4
        if emergency is not None:
            fields = {"N", "S", "E", "W"}
            if traffic_state is None or approach_state is None:
                raise ValueError("emergency requires traffic_state and approach_state")
            if not isinstance(emergency, dict) or set(emergency) != fields:
                raise ValueError("emergency must contain all observation v5 emergency fields")
            for approach in fields:
                value = emergency[approach]
                if (isinstance(value, bool) or not isinstance(value, (int, float))
                        or value not in (0, 1)):
                    raise ValueError("emergency values must be 0 or 1")
            if sum(emergency[a] for a in fields) > 1:
                raise ValueError("emergency may flag at most one approach")
            observation["emergency"] = emergency
            observation["schema_version"] = 5
        if class_counts is not None:
            approaches = {"N", "S", "E", "W"}
            classes = {"car", "motorcycle", "bicycle", "bus", "truck"}
            if not isinstance(class_counts, dict) or set(class_counts) != approaches:
                raise ValueError("class_counts must contain all observation v6 approach fields")
            for approach in sorted(approaches):
                breakdown = class_counts[approach]
                if not isinstance(breakdown, dict) or set(breakdown) != classes:
                    raise ValueError(f"class_counts.{approach} must contain exactly car, motorcycle, bicycle, bus, truck")
                for name in sorted(classes):
                    value = breakdown[name]
                    if (isinstance(value, bool) or not isinstance(value, (int, float))
                            or not 0 <= value <= 500 or int(value) != value):
                        raise ValueError("class_counts values must be whole numbers in 0..500")
            observation["class_counts"] = class_counts
            observation["schema_version"] = 6
        body = json.dumps(observation, allow_nan=False).encode()
        request = urllib.request.Request(self.endpoint + "/v1/observations", body,
                    {"Content-Type": "application/json", "Authorization": "Bearer " + self.token}, method="POST")
        dispatched = time.perf_counter()
        with self.opener.open(request, timeout=2) as response:
            result = json.load(response)
        completed = time.perf_counter()
        self.last_timings = {"sequence_reservation_ms": (reserved-started)*1000,
                             "serialization_ms": (dispatched-reserved)*1000,
                             "http_acceptance_ms": (completed-dispatched)*1000,
                             "submission_total_ms": (completed-started)*1000}
        return result

    def close(self):
        self.db.close()
