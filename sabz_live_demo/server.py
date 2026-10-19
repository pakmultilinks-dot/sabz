"""SABZ interactive live demo: real camera footage, live AI vehicle detection,
and the trained DQN brain deciding signal phases from what it sees.

Run:  python3 server.py        ->  http://localhost:8099
"""
import base64
import os
import sys
import threading
import time

import cv2
import numpy as np
from flask import Flask, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)
sys.path.insert(0, WORK)

from sabz_rl import load_net, state_vec_from_dict  # noqa: E402

VIDEO_PATH = os.path.join(WORK, "real_footage", "traffic_cam.mp4")
BRAIN_PATH = os.path.join(WORK, "sabz_dqn_best.npz")
MIN_GREEN = 5.0          # seconds of green before the brain may switch
BRAIN_EVERY = 30         # frames between brain queries (1s at 30fps)

app = Flask(__name__)

# ---------------------------------------------------------------- state ----
net = load_net(BRAIN_PATH)
print("brain loaded:", BRAIN_PATH, flush=True)

cap_probe = cv2.VideoCapture(VIDEO_PATH)
FPS = cap_probe.get(cv2.CAP_PROP_FPS) or 30.0
TOTAL = int(cap_probe.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
FW = int(cap_probe.get(cv2.CAP_PROP_FRAME_WIDTH))
FH = int(cap_probe.get(cv2.CAP_PROP_FRAME_HEIGHT))
cap_probe.release()
print(f"video: {FW}x{FH} {FPS:.1f}fps {TOTAL} frames", flush=True)


class Demo:
    def __init__(self):
        self.lock = threading.Lock()
        self.cap = cv2.VideoCapture(VIDEO_PATH)
        self.bg = cv2.createBackgroundSubtractorMOG2(
            history=120, varThreshold=40, detectShadows=False)
        self.kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self.frame_idx = 0
        self.playing = True
        self.speed = 1
        self.phase = "NS"
        self.green_elapsed = 0.0
        self.last_switch_frame = 0
        self.switches = 0
        self.q_hold = 0.0
        self.q_switch = 0.0
        self.decision = "HOLD"
        self.boxes = []          # [x, y, w, h] in frame pixels
        self.count = 0
        self.queues = {"N": 0, "S": 0, "E": 0, "W": 0}
        self.first_seen = {"N": None, "S": None, "E": None, "W": None}
        self.jpeg = b""
        self.t0 = time.time()

    def reset(self):
        with self.lock:
            self.cap.release()
            self.cap = cv2.VideoCapture(VIDEO_PATH)
            self.bg = cv2.createBackgroundSubtractorMOG2(
                history=120, varThreshold=40, detectShadows=False)
            self.frame_idx = 0
            self.phase = "NS"
            self.green_elapsed = 0.0
            self.last_switch_frame = 0
            self.switches = 0
            self.q_hold = 0.0
            self.q_switch = 0.0
            self.decision = "HOLD"
            self.boxes = []
            self.count = 0
            self.queues = {"N": 0, "S": 0, "E": 0, "W": 0}
            self.first_seen = {"N": None, "S": None, "E": None, "W": None}
            self.t0 = time.time()

    def quadrant(self, x, y):
        if x < FW / 2:
            return "N" if y < FH / 2 else "W"
        return "E" if y < FH / 2 else "S"

    def detect(self, frame):
        fg = self.bg.apply(frame)
        _, fg = cv2.threshold(fg, 200, 255, cv2.THRESH_BINARY)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, self.kernel)
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, self.kernel)
        contours, _ = cv2.findContours(
            fg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        boxes = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < 800 or area > 60000:
                continue
            x, y, w, h = cv2.boundingRect(c)
            aspect = w / max(h, 1)
            if aspect < 0.35 or aspect > 4.5:
                continue
            boxes.append([int(x), int(y), int(w), int(h)])
        return boxes

    def brain_step(self):
        """Ask the trained DQN whether to hold or switch, from live counts."""
        q = self.queues
        red_wait = min((self.frame_idx - self.last_switch_frame) / FPS / 300.0, 2.0)
        max_age = 0.0
        now_f = self.frame_idx
        for a in ("N", "S", "E", "W"):
            if q[a] > 0:
                if self.first_seen[a] is None:
                    self.first_seen[a] = now_f
                age = (now_f - self.first_seen[a]) / FPS / 300.0
                max_age = max(max_age, min(age, 2.0))
            else:
                self.first_seen[a] = None
        state = {
            "queue": {a: float(q[a]) for a in ("N", "S", "E", "W")},
            "approaching": {a: float(q[a]) for a in ("N", "S", "E", "W")},
            "phase": self.phase,
            "green_elapsed": float(self.green_elapsed),
            "red_wait": float(red_wait),
            "max_q_age": float(max_age),
        }
        vec = state_vec_from_dict(state)
        qv, _ = net.forward(vec)
        qv = np.asarray(qv).flatten()
        self.q_hold, self.q_switch = float(qv[0]), float(qv[1])
        action = int(np.argmax(qv))
        if action == 1 and self.green_elapsed >= MIN_GREEN:
            self.phase = "EW" if self.phase == "NS" else "NS"
            self.green_elapsed = 0.0
            self.last_switch_frame = self.frame_idx
            self.switches += 1
            self.decision = "SWITCH"
        else:
            self.decision = "HOLD"

    def annotate(self, frame):
        for (x, y, w, h) in self.boxes:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 230, 118), 2)
            cv2.circle(frame, (x + 10, y - 10), 5, (0, 230, 118), -1)
        # top-left count chip
        cv2.rectangle(frame, (12, 12), (250, 52), (5, 8, 14), -1)
        cv2.putText(frame, f"VEHICLES: {self.count}", (24, 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 230, 118), 2)
        # phase chip bottom-left
        col = (0, 230, 118)
        label = f"{self.phase} GREEN"
        (tw, _), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
        cv2.rectangle(frame, (12, FH - 56), (24 + tw, FH - 16), (5, 8, 14), -1)
        cv2.putText(frame, label, (24, FH - 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, col, 2)
        return frame

    def run(self):
        while True:
            with self.lock:
                playing, speed = self.playing, self.speed
            if not playing:
                time.sleep(0.05)
                continue
            t_start = time.time()
            with self.lock:
                if self.frame_idx >= TOTAL:
                    # seamless loop
                    self.cap.release()
                    self.cap = cv2.VideoCapture(VIDEO_PATH)
                    self.bg = cv2.createBackgroundSubtractorMOG2(
                        history=120, varThreshold=40, detectShadows=False)
                    self.frame_idx = 0
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.frame_idx)
                ret, frame = self.cap.read()
                if not ret:
                    self.frame_idx = 0
                    continue
                boxes = self.detect(frame)
                self.boxes = boxes
                self.count = len(boxes)
                qs = {"N": 0, "S": 0, "E": 0, "W": 0}
                for (x, y, w, h) in boxes:
                    qs[self.quadrant(x + w / 2, y + h / 2)] += 1
                self.queues = qs
                if self.frame_idx % BRAIN_EVERY == 0 and self.frame_idx > 0:
                    self.brain_step()
                    self.green_elapsed += 1.0
                annotated = self.annotate(frame.copy())
                ok, buf = cv2.imencode(".jpg", annotated,
                                       [cv2.IMWRITE_JPEG_QUALITY, 82])
                if ok:
                    self.jpeg = buf.tobytes()
                self.frame_idx += 1
            # pace to video fps * speed
            dt = time.time() - t_start
            target = max(0.0, 1.0 / (FPS * speed) - dt)
            time.sleep(target)

    def snapshot(self):
        with self.lock:
            return {
                "frame": self.frame_idx,
                "total_frames": TOTAL,
                "fps": FPS,
                "playing": self.playing,
                "speed": self.speed,
                "vehicle_count": self.count,
                "boxes": self.boxes,
                "queues": dict(self.queues),
                "q_hold": round(self.q_hold, 3),
                "q_switch": round(self.q_switch, 3),
                "decision": self.decision,
                "phase": self.phase,
                "green_elapsed": round(self.green_elapsed, 1),
                "switches": self.switches,
            }

    def frame_b64(self):
        with self.lock:
            if not self.jpeg:
                return None
            return base64.b64encode(self.jpeg).decode("ascii")


demo = Demo()
worker = threading.Thread(target=demo.run, daemon=True)
worker.start()
# warm up: let a few frames process so /api/frame is never empty
time.sleep(1.5)


@app.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.route("/fonts/<path:p>")
def fonts(p):
    return send_from_directory(os.path.join(HERE, "fonts"), p)


@app.route("/api/state")
def api_state():
    return jsonify(demo.snapshot())


@app.route("/api/frame")
def api_frame():
    b64 = demo.frame_b64()
    if b64 is None:
        return jsonify({"error": "warming up"}), 503
    return jsonify({"frame": demo.snapshot()["frame"], "jpeg": b64})


@app.route("/api/control", methods=["POST"])
def api_control():
    body = request.get_json(force=True, silent=True) or {}
    with demo.lock:
        if "playing" in body:
            demo.playing = bool(body["playing"])
        if "speed" in body:
            try:
                demo.speed = max(1, min(4, int(body["speed"])))
            except (TypeError, ValueError):
                pass
    if body.get("restart"):
        demo.reset()
    return jsonify(demo.snapshot())


if __name__ == "__main__":
    print("SABZ live demo on http://localhost:8099", flush=True)
    app.run(host="0.0.0.0", port=8099, threaded=True)
