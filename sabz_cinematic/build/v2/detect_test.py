#!/usr/bin/env python3
"""YOLOv8 detection test on 2 sample frames (ONNX runtime, no torch)."""
import cv2
import numpy as np
import onnxruntime as ort
import sys

MODEL = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_cinematic/build/v2/yolov8n.onnx"
VEHICLES = {1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
CONF = 0.35

sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
inp_name = sess.get_inputs()[0].name


def detect(frame):
    h, w = frame.shape[:2]
    img = cv2.resize(frame, (640, 640)).astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))[None]
    out = sess.run(None, {inp_name: img})[0]  # (1, 84, 8400)
    pred = out[0].T  # (8400, 84)
    boxes, scores, classes = [], [], []
    for row in pred:
        cls_scores = row[4:]
        c = int(np.argmax(cls_scores))
        s = float(cls_scores[c])
        if s < CONF or c not in VEHICLES:
            continue
        cx, cy, bw, bh = row[0], row[1], row[2], row[3]
        x1 = int((cx - bw / 2) / 640 * w)
        y1 = int((cy - bh / 2) / 640 * h)
        x2 = int((cx + bw / 2) / 640 * w)
        y2 = int((cy + bh / 2) / 640 * h)
        boxes.append([x1, y1, x2 - x1, y2 - y1])
        scores.append(s)
        classes.append(c)
    if boxes:
        idxs = cv2.dnn.NMSBoxes(boxes, scores, CONF, 0.45)
        keep = [int(i) for i in np.array(idxs).flatten()] if len(idxs) else []
    else:
        keep = []
    return [(boxes[i], scores[i], classes[i]) for i in keep]


for path in sys.argv[1:]:
    frame = cv2.imread(path)
    dets = detect(frame)
    print(path, "->", len(dets), "vehicles")
    for (x, y, bw, bh), s, c in dets:
        print(f"   {VEHICLES[c]:10s} {s:.2f} box=({x},{y},{bw},{bh})")
        cv2.rectangle(frame, (x, y), (x + bw, y + bh), (118, 230, 0), 3)
        label = f"{VEHICLES[c]} {s:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(frame, (x, y - th - 10), (x + tw + 8, y), (118, 230, 0), -1)
        cv2.putText(frame, label, (x + 4, y - 5), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (10, 10, 10), 2)
    cv2.imwrite(path.replace(".jpg", "_det.jpg"), frame)
print("done")
