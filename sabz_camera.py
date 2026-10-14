"""SABZ live video system: YOLO vehicle detection on real video streams.

Built for LIVE VIDEO, not static images. Handles:
- Webcam / USB camera (source=0)
- RTSP network streams (source="rtsp://...")
- Video files (source="path/to/video.mp4")
- YouTube / HTTP streams

Pipeline per frame:
    Video frame -> YOLO detect -> track across frames -> count per approach
    -> Intelligence Layer -> Safety check -> signal decision

Vehicle tracking across frames prevents double-counting the same car.
"""
import cv2
import numpy as np
import time
from collections import defaultdict

try:
    from ultralytics import YOLO
    _YOLO_OK = True
except ImportError:
    _YOLO_OK = False


class VehicleTracker:
    """Simple centroid tracker: match detections across frames by distance."""

    def __init__(self, max_dist=60, max_missing=10):
        self.max_dist = max_dist
        self.max_missing = max_missing
        self.tracks = {}  # id -> {cx, cy, missing, approach}
        self.next_id = 0

    def update(self, detections):
        """detections: list of (cx, cy) in pixels. Returns dict of track ids."""
        # Match each detection to nearest existing track
        used = set()
        matched = {}
        for cx, cy in detections:
            best_id, best_d = None, self.max_dist
            for tid, t in self.tracks.items():
                if tid in used:
                    continue
                d = ((cx - t["cx"]) ** 2 + (cy - t["cy"]) ** 2) ** 0.5
                if d < best_d:
                    best_d, best_id = d, tid
            if best_id is not None:
                matched[best_id] = (cx, cy)
                used.add(best_id)
            else:
                tid = self.next_id
                self.next_id += 1
                self.tracks[tid] = {"cx": cx, "cy": cy, "missing": 0}
                matched[tid] = (cx, cy)
                used.add(tid)

        # Update matched, age out missing
        for tid in list(self.tracks.keys()):
            if tid in matched:
                cx, cy = matched[tid]
                self.tracks[tid].update(cx=cx, cy=cy, missing=0)
            else:
                self.tracks[tid]["missing"] += 1
                if self.tracks[tid]["missing"] > self.max_missing:
                    del self.tracks[tid]
        return matched


class LiveCameraSystem:
    """Live video processing with tracking and per-approach counting."""

    def __init__(self, yolo="yolov8n.pt", frame_skip=3, conf=0.35):
        if not _YOLO_OK:
            raise RuntimeError("ultralytics not installed")
        self.detector = YOLO(yolo)
        self.vehicle_ids = [2, 3, 5, 7]  # car, motorcycle, bus, truck
        self.frame_skip = frame_skip
        self.conf = conf
        self.tracker = VehicleTracker()
        # Approach regions (normalized); calibrate per camera
        self.regions = {
            "N": [(0.3, 0.0), (0.7, 0.0), (0.7, 0.4), (0.3, 0.4)],
            "S": [(0.3, 0.6), (0.7, 0.6), (0.7, 1.0), (0.3, 1.0)],
            "E": [(0.6, 0.3), (1.0, 0.3), (1.0, 0.7), (0.6, 0.7)],
            "W": [(0.0, 0.3), (0.4, 0.3), (0.4, 0.7), (0.0, 0.7)],
        }
        self.frame_num = 0
        self.fps = 0.0
        self._t0 = time.time()

    def _point_in_poly(self, x, y, poly):
        n, inside, j = len(poly), False, len(poly) - 1
        for i in range(n):
            if ((poly[i][1] > y) != (poly[j][1] > y) and
                    x < (poly[j][0] - poly[i][0]) * (y - poly[i][1]) /
                    (poly[j][1] - poly[i][1]) + poly[i][0]):
                inside = not inside
            j = i
        return inside

    def process_frame(self, frame):
        """Run detection + tracking on one frame. Returns per-approach counts."""
        h, w = frame.shape[:2]
        self.frame_num += 1

        # Only run YOLO every frame_skip frames; track in between
        detections = []
        if self.frame_num % self.frame_skip == 0:
            results = self.detector(frame, verbose=False, conf=self.conf)[0]
            for box in results.boxes:
                if int(box.cls[0]) in self.vehicle_ids:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    detections.append(((x1 + x2) / 2, (y1 + y2) / 2))

        tracks = self.tracker.update(detections)

        # Count unique tracked vehicles per approach region
        counts = {a: 0 for a in ("N", "S", "E", "W")}
        for tid, t in self.tracker.tracks.items():
            nx, ny = t["cx"] / w, t["cy"] / h
            for app, poly in self.regions.items():
                if self._point_in_poly(nx, ny, poly):
                    counts[app] += 1
                    break

        # FPS
        dt = time.time() - self._t0
        if dt > 0:
            self.fps = self.frame_num / dt
        return counts, len(self.tracker.tracks)

    def run_stream(self, source, on_counts=None, max_frames=0, show=False):
        """Process a live video stream.

        source: 0 (webcam), "rtsp://...", or video file path.
        on_counts: callback(counts_dict) called each processed frame.
        max_frames: stop after N frames (0 = unlimited).
        show: display annotated window (needs display).
        Returns list of per-second count snapshots.
        """
        cap = cv2.VideoCapture(source)
        if not cap.isOpened():
            raise RuntimeError(f"cannot open video source: {source}")

        snapshots = []
        last_snap = time.time()
        n = 0
        print(f"SABZ live video running on {source}. Ctrl+C to stop.")
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    print("stream ended")
                    break
                counts, tracked = self.process_frame(frame)
                n += 1

                # Snapshot once per second
                if time.time() - last_snap >= 1.0:
                    snapshots.append(dict(counts))
                    last_snap = time.time()
                    if on_counts:
                        on_counts(counts)

                if show:
                    cv2.putText(frame,
                                f"N:{counts['N']} S:{counts['S']} "
                                f"E:{counts['E']} W:{counts['W']} "
                                f"({self.fps:.0f}fps)",
                                (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                                0.7, (0, 255, 0), 2)
                    cv2.imshow("SABZ Live", frame)
                    if cv2.waitKey(1) & 0xFF == ord("q"):
                        break

                if max_frames and n >= max_frames:
                    break
        except KeyboardInterrupt:
            print("stopped by user")
        finally:
            cap.release()
            if show:
                cv2.destroyAllWindows()
        print(f"processed {n} frames, {len(snapshots)} one-second snapshots")
        return snapshots


# Backwards-compatible alias
CameraSystem = LiveCameraSystem


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else 0
    try:
        src = int(src)
    except ValueError:
        pass
    cam = LiveCameraSystem()
    cam.run_stream(src, on_counts=lambda c: print(c, flush=True))
