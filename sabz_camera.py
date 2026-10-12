"""SABZ real-time camera system: YOLO vehicle detection + DQN brain.

Takes live camera footage, detects vehicles per approach using YOLOv8,
feeds counts to the trained DQN brain, and outputs signal decisions.
This is REAL computer vision, not simulation.
"""
import cv2
import numpy as np
from ultralytics import YOLO


class CameraSystem:
    def __init__(self, model_path="sabz_dqn_final.npz", yolo="yolov8n.pt"):
        # Load YOLO for vehicle detection
        self.detector = YOLO(yolo)
        # Vehicle classes in COCO: car, motorcycle, bus, truck
        self.vehicle_ids = [2, 3, 5, 7]
        # Load our trained brain
        self.brain = self._load_brain(model_path)
        # Define 4 approach regions (normalized coordinates)
        # These should be calibrated per camera installation
        self.regions = {
            "N": [(0.3, 0.0), (0.7, 0.0), (0.7, 0.4), (0.3, 0.4)],
            "S": [(0.3, 0.6), (0.7, 0.6), (0.7, 1.0), (0.3, 1.0)],
            "E": [(0.6, 0.3), (1.0, 0.3), (1.0, 0.7), (0.6, 0.7)],
            "W": [(0.0, 0.3), (0.4, 0.3), (0.4, 0.7), (0.0, 0.7)],
        }

    def _load_brain(self, path):
        """Load our trained DQN weights."""
        import sabz_rl as R
        net = R.DQN()
        d = np.load(path)
        # Handle both old (p_) and new (net_) key formats
        for k in net.p:
            key = f"net_{k}" if f"net_{k}" in d else f"p_{k}"
            if key in d:
                net.p[k] = d[key]
        return net

    def detect_vehicles(self, frame):
        """Run YOLO, return vehicle detections."""
        results = self.detector(frame, verbose=False)[0]
        vehicles = []
        for box in results.boxes:
            cls = int(box.cls[0])
            if cls in self.vehicle_ids:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                vehicles.append((cx / frame.shape[1], cy / frame.shape[0]))
        return vehicles

    def count_by_approach(self, vehicles):
        """Count vehicles in each approach region."""
        counts = {a: 0 for a in ("N", "S", "E", "W")}
        for cx, cy in vehicles:
            for app, poly in self.regions.items():
                if self._point_in_poly(cx, cy, poly):
                    counts[app] += 1
                    break
        return counts

    def _point_in_poly(self, x, y, poly):
        n = len(poly)
        inside = False
        j = n - 1
        for i in range(n):
            if ((poly[i][1] > y) != (poly[j][1] > y) and
                    x < (poly[j][0] - poly[i][0]) * (y - poly[i][1]) /
                    (poly[j][1] - poly[i][1]) + poly[i][0]):
                inside = not inside
            j = i
        return inside

    def decide(self, counts, phase="NS", green_elapsed=0):
        """Brain decides: 0=hold, 1=switch."""
        import sabz_rl as R
        # Build 16-dim state (10 traffic + 6 location)
        # Location defaults to neutral for camera mode
        q = [counts[a] / 20.0 for a in ("N", "S", "E", "W")]
        ap = [counts[a] / 10.0 for a in ("N", "S", "E", "W")]  # approaching = queued for camera
        loc = [0.0] * R.N_POI
        s = np.array(q + ap + [1.0 if phase == "NS" else 0.0,
                              green_elapsed / 60.0] + loc)
        return self.brain.act(s)

    def process_frame(self, frame, phase="NS", green_elapsed=0):
        """Full pipeline: detect -> count -> decide."""
        vehicles = self.detect_vehicles(frame)
        counts = self.count_by_approach(vehicles)
        action = self.decide(counts, phase, green_elapsed)
        return {
            "counts": counts,
            "total": len(vehicles),
            "action": "switch" if action == 1 else "hold",
            "vehicles": vehicles,
        }


def run_camera(source=0, model="sabz_dqn_final.npz"):
    """Run on live camera or video file."""
    system = CameraSystem(model_path=model)
    cap = cv2.VideoCapture(source)
    phase, green_elapsed = "NS", 0

    print("SABZ camera system running. Press 'q' to quit.")
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        result = system.process_frame(frame, phase, green_elapsed)
        # Overlay info on frame
        cv2.putText(frame, f"N:{result['counts']['N']} S:{result['counts']['S']} "
                           f"E:{result['counts']['E']} W:{result['counts']['W']}",
                    (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"Decision: {result['action'].upper()}",
                    (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        cv2.imshow("SABZ Live", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        green_elapsed += 1/30  # assume 30fps
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else 0
    try:
        src = int(src)
    except ValueError:
        pass  # video file path
    run_camera(source=src)
