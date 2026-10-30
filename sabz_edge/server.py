"""Bounded HTTPS API. No endpoint accepts lamp commands or learning feedback."""
import argparse
import hashlib
import http.client
import hmac
import ipaddress
import json
import os
from pathlib import Path
import signal
import socket
import ssl
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .core import Observation, Timing
from .runtime import Runtime
from .guard import CabinetAdapter
from .store import InstanceLock, ReplayError, Store

MAX_BODY = 4096
MAX_HEADERS = 16384
REQUEST_DEADLINE = 3.0
MAX_DISCARD = 65536


class HeaderBudget:
    def __init__(self, stream):
        self.stream, self.remaining = stream, MAX_HEADERS

    def readline(self, size=-1):
        line = self.stream.readline(min(size, self.remaining + 1) if size >= 0 else self.remaining + 1)
        self.remaining -= len(line)
        if self.remaining < 0:
            raise http.client.HTTPException("aggregate header limit exceeded")
        return line


def load_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError("non-finite JSON number")
    return json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)


class Settings:
    def __init__(self, env=None):
        env = os.environ if env is None else env
        self.host = env.get("SABZ_BIND", "127.0.0.1")
        self.port = int(env.get("SABZ_PORT", "8099"))
        if not 0 <= self.port <= 65535:
            raise ValueError("invalid SABZ_PORT")
        address = ipaddress.ip_address(self.host)
        self.camera_token = env.get("SABZ_CAMERA_TOKEN", "")
        self.reader_token = env.get("SABZ_READER_TOKEN", "")
        if any(len(t) < 32 or len(t) > 256 or not t.isascii() or any(c.isspace() for c in t)
               for t in (self.camera_token, self.reader_token)):
            raise ValueError("set distinct ASCII tokens of 32..256 characters")
        if self.camera_token == self.reader_token:
            raise ValueError("camera and reader credentials must differ")
        self.cert = env.get("SABZ_TLS_CERT")
        self.key = env.get("SABZ_TLS_KEY")
        if bool(self.cert) != bool(self.key):
            raise ValueError("TLS certificate and key must both be configured")
        if not address.is_loopback and not self.cert:
            raise ValueError("non-loopback binding requires TLS")
        self.source_id = env.get("SABZ_SOURCE_ID", "intersection-1-camera")
        if not self.source_id or len(self.source_id) > 100:
            raise ValueError("invalid source ID")
        self.state_path = env.get("SABZ_STATE_PATH", "data/edge.sqlite3")
        timing_path = env.get("SABZ_TIMING_FILE")
        self.timing = Timing(**load_json(Path(timing_path).read_text(encoding="utf-8"))) if timing_path else Timing()


class Limiter:
    """Global token bucket shared by callers; fixed memory footprint."""
    def __init__(self, rate=20, burst=40):
        self.rate, self.burst = rate, burst
        self.tokens = float(burst)
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def allow(self):
        with self.lock:
            now = time.monotonic()
            self.tokens = min(self.burst, self.tokens + (now - self.last) * self.rate)
            self.last = now
            if self.tokens < 1:
                return False
            self.tokens -= 1
            return True


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 16

    def __init__(self, settings, runtime):
        self.settings, self.runtime = settings, runtime
        self.limiter = Limiter()
        self.slots = threading.BoundedSemaphore(16)
        self.camera_hash = hashlib.sha256(settings.camera_token.encode()).digest()
        self.reader_hash = hashlib.sha256(settings.reader_token.encode()).digest()
        self.address_family = socket.AF_INET6 if ":" in settings.host else socket.AF_INET
        self.tls_context = None
        if settings.cert:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(settings.cert, settings.key)
            self.tls_context = context
        super().__init__((settings.host, settings.port), Handler)

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        def expire():
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        deadline = threading.Timer(REQUEST_DEADLINE, expire)
        deadline.daemon = True
        deadline.start()
        try:
            request.settimeout(2)
            if self.tls_context:
                request = self.tls_context.wrap_socket(request, server_side=True)
            super().process_request_thread(request, address)
        except (OSError, ssl.SSLError):
            self.shutdown_request(request)
        finally:
            deadline.cancel()
            self.slots.release()

    def handle_error(self, request, client_address):
        pass  # Never log credentials or payloads through exception traces.


class Handler(BaseHTTPRequestHandler):
    server_version = "SABZ-Edge"
    sys_version = ""
    protocol_version = "HTTP/1.0"

    def parse_request(self):
        if len(self.raw_requestline) > 2048:
            self.requestline = ""
            self.request_version = "HTTP/1.0"
            self.command = None
            self.send_error(414)
            return False
        stream = self.rfile
        try:
            self.rfile = HeaderBudget(stream)
            valid = super().parse_request()
        finally:
            self.rfile = stream
        self._body_remaining = 0
        if valid:
            lengths = self.headers.get_all("Content-Length", [])
            if len(lengths) == 1 and lengths[0].isascii() and lengths[0].isdecimal() and len(lengths[0]) <= 10:
                length = int(lengths[0])
                if 0 <= length <= MAX_DISCARD and not self.headers.get("Transfer-Encoding"):
                    self._body_remaining = length
        if valid and not self.server.limiter.allow():
            self._send(429, {"error": "rate_limited"})
            return False
        return valid

    def log_message(self, *args):
        pass

    def _send(self, code, body, content_type="application/json"):
        encoded = body.encode("utf-8") if content_type.startswith("text/html") else json.dumps(body, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Security-Policy", "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(encoded)
        # Closing with a still-arriving body can reset TCP on Windows before
        # the client receives an otherwise valid 401/404/413 response. Discard
        # only bounded, unambiguously framed bytes, without parsing them.
        remaining = getattr(self, "_body_remaining", 0)
        if remaining:
            try:
                self.connection.settimeout(.1)
                self.rfile.read(remaining)
            except (OSError, ValueError):
                pass
            self._body_remaining = 0
        self.close_connection = True

    def _gate(self, role):
        headers = self.headers.get_all("Authorization", [])
        value = headers[0] if len(headers) == 1 else ""
        if not value.startswith("Bearer ") or len(value) > 263:
            self._send(401, {"error": "unauthorized"})
            return False
        token_hash = hashlib.sha256(value[7:].encode()).digest()
        expected = self.server.camera_hash if role == "camera" else self.server.reader_hash
        if not hmac.compare_digest(token_hash, expected):
            self._send(401, {"error": "unauthorized"})
            return False
        return True

    def do_GET(self):
        if self.path == "/":
            self._send(200, """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SABZ edge service</title></head>
<body><main><h1>SABZ edge service</h1>
<p>This address runs the traffic-control API. It is not the simulation website or an operator dashboard.</p>
<p><strong>Bench mode: signal outputs are emulated. No road lamps are connected by this service.</strong></p>
<h2>Check this installation</h2>
<p><a href="/healthz">Check service liveness</a>. Liveness does not mean sensors or signal control are ready.</p>
<p>For authenticated operational status, run this command from the repository directory:</p>
<pre>python deploy/local_instance.py status --directory data/local-installation</pre>
<p>The utility reads protected local credentials and verifies HTTPS. Do not paste credentials into browser URLs.</p>
<h2>API routes</h2><ul><li>GET /v1/status: reader authentication required.</li>
<li>GET /v1/metrics: reader authentication required (dashboard metric stream).</li>
<li>GET /readyz: reader authentication required.</li><li>POST /v1/observations: sensor authentication required.</li>
<li>POST /v1/telemetry: sensor authentication required (counts-only dashboard feed).</li>
<li>POST /v1/preemption: reader authentication required.</li></ul>
<p>Without a healthy sensor feed, the service is not ready and the emulator holds all-red after clearance.</p>
</main></body></html>""".replace("Bench mode: signal outputs are emulated. No road lamps are connected by this service.",
                "Low-voltage LED bench mode. GPIO readback only; road lamp operation is unsupported."
                if getattr(self.server.runtime.adapter, "physical_hardware", False) else
                "Bench mode: signal outputs are emulated. No road lamps are connected by this service."), "text/html; charset=utf-8")
            return
        if self.path == "/healthz":
            thread = self.server.runtime.thread
            last = self.server.runtime.last_completed_tick
            alive = (thread is not None and thread.is_alive() and last is not None
                     and 0 <= self.server.runtime.clock() - last <= self.server.runtime.controller.timing.max_tick_gap)
            self._send(200 if alive else 503, {"alive": alive})
            return
        if self.path not in ("/v1/status", "/readyz", "/v1/metrics"):
            self._send(404, {"error": "not_found"})
            return
        if not self._gate("reader"):
            return
        if self.path == "/v1/metrics":
            self._send(200, self.server.runtime.metrics_snapshot())
            return
        status = self.server.runtime.status()
        self._send(200 if self.path == "/v1/status" or status["ready"] else 503, status)

    def do_POST(self):
        if self.path not in ("/v1/observations", "/v1/preemption", "/v1/telemetry"):
            self._send(404, {"error": "not_found"})
            return
        if not self._gate("camera" if self.path in ("/v1/observations", "/v1/telemetry") else "reader"):
            return
        if self.headers.get_content_type() != "application/json":
            self._send(415, {"error": "application_json_required"})
            return
        lengths = self.headers.get_all("Content-Length", [])
        if self.headers.get("Transfer-Encoding") or len(lengths) != 1:
            self._send(400, {"error": "one_content_length_required"})
            return
        try:
            if not lengths[0].isascii() or not lengths[0].isdecimal() or len(lengths[0]) > 10:
                raise ValueError("invalid length")
            length = int(lengths[0])
            if not 1 <= length <= MAX_BODY:
                self._send(413, {"error": "body_size_limit"})
                return
            raw = self.rfile.read(length)
            self._body_remaining = max(0, self._body_remaining - len(raw))
            if len(raw) != length:
                raise ValueError("incomplete body")
            if self.path == "/v1/preemption":
                data = load_json(raw)
                if not isinstance(data, dict) or set(data) != {"approach"}:
                    raise ValueError("preemption body must be exactly {\"approach\": ...}")
                approach = data["approach"]
                if not isinstance(approach, str) or approach not in ("N", "S", "E", "W"):
                    raise ValueError("approach must be N, S, E or W")
                self.server.runtime.preempt(approach)
                self._send(202, {"accepted": True, "approach": approach, "mode": "bench"})
                return
            if self.path == "/v1/telemetry":
                data = load_json(raw)
                if not isinstance(data, dict) or set(data) != {"counts", "conflict_clear", "healthy"}:
                    raise ValueError("telemetry body must be exactly {counts, conflict_clear, healthy}")
                if not isinstance(data["counts"], dict) or set(data["counts"]) != {"N", "S", "E", "W"}:
                    raise ValueError("counts must contain exactly N, S, E, W")
                if type(data["conflict_clear"]) is not bool or type(data["healthy"]) is not bool:
                    raise ValueError("conflict_clear and healthy must be booleans")
                sequence = self.server.runtime.submit_telemetry(
                    data["counts"], data["conflict_clear"], data["healthy"])
                self._send(202, {"accepted_sequence": sequence, "mode": "bench"})
                return
            observation = Observation.parse(load_json(raw), self.server.runtime.wall())
            self.server.runtime.submit(self.server.settings.source_id, observation)
        except ReplayError:
            self._send(409, {"error": "sequence_replayed"})
            return
        except (ValueError, TypeError, UnicodeError, RecursionError):
            self._send(400, {"error": "invalid_observation"})
            return
        except (TimeoutError, OSError):
            self._send(408, {"error": "request_timeout"})
            return
        except Exception:
            with self.server.runtime.lock:
                self.server.runtime.controller.trip("observation_storage_failure")
            self._send(503, {"error": "service_fault"})
            return
        self._send(202, {"accepted_sequence": observation.sequence, "mode": "bench"})


def main():
    argparse.ArgumentParser(description="SABZ bench edge service; configure via environment").parse_args()
    settings = Settings()
    Path(settings.state_path).parent.mkdir(parents=True, exist_ok=True)
    with InstanceLock(settings.state_path + ".lock"):
        run(settings)


def run(settings, adapter_factory=None):
    adapter = store = runtime = server = None
    try:
        # Spawn the cabinet before opening SQLite so no native database
        # handles can be inherited through a platform interpreter launcher.
        adapter = (adapter_factory or CabinetAdapter)(settings.timing)
        store = Store(settings.state_path)
        runtime = Runtime(store, settings.timing)
        runtime.adapter = adapter
        state_dir = os.path.dirname(os.path.abspath(settings.state_path))
        runtime.set_alert_log(os.path.join(state_dir, "alerts.jsonl"))
        store.event("startup", {"mode": "bench", "timing": settings.timing.__dict__, "source": settings.source_id, "adapter": adapter.name})
        server = Server(settings, runtime)
        runtime.start()
        def stop(*_):
            threading.Thread(target=server.shutdown, daemon=True).start()
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        print(f"SABZ edge on {settings.host}:{settings.port}; mode=bench; adapter={adapter.name}; field_ready=false", flush=True)
        server.serve_forever(poll_interval=0.2)
    finally:
        if server:
            server.server_close()
        if runtime:
            runtime.close()
        else:
            if adapter:
                adapter.close()
            if store:
                store.close()


if __name__ == "__main__":
    main()
