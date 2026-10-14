"""SABZ Integration API: REST service for real-world deployment.

Plug any camera feed and any signal controller into SABZ through HTTP.
The model never talks to hardware directly; everything goes through this API.

Endpoints:
    POST /camera      {N, S, E, W} vehicle counts -> {action, controller}
    GET  /status      current signal state and routing stats
    POST /feedback    {delay} report observed delay for learning
    GET  /health      service health check

Run:  python3 sabz_api.py  (listens on port 8099)
"""
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from sabz_intelligence import IntelligenceLayer, SignalIntegration

PORT = 8099

# Global brain instance
_brain = IntelligenceLayer()
_signal = SignalIntegration(_brain)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}

    def do_POST(self):
        if self.path == "/camera":
            data = self._read_body()
            counts = {k: float(data.get(k, 0)) for k in ["N", "S", "E", "W"]}
            action = _signal.on_camera_frame(counts)
            self._send(200, {
                "action": action,
                "controller": _signal.last_controller,
                "ts": time.time(),
            })
        elif self.path == "/feedback":
            data = self._read_body()
            _brain.report(
                data.get("controller", "actuated"),
                data.get("regime", "normal"),
                float(data.get("delay", 0)),
            )
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "unknown endpoint"})

    def do_GET(self):
        if self.path == "/status":
            self._send(200, {
                "last_decision": _signal.last_decision,
                "last_controller": _signal.last_controller,
                "stats": _brain.stats(),
                "ts": time.time(),
            })
        elif self.path == "/health":
            self._send(200, {"ok": True, "ts": time.time()})
        else:
            self._send(404, {"error": "unknown endpoint"})

    def log_message(self, *args):
        pass  # quiet


def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"SABZ integration API on port {PORT}")
    print("  POST /camera   {N,S,E,W} -> {action, controller}")
    print("  GET  /status")
    print("  POST /feedback {controller, regime, delay}")
    server.serve_forever()


if __name__ == "__main__":
    main()
