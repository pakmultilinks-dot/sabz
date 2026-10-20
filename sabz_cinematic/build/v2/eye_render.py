#!/usr/bin/env python3
"""THE EYE: YOLOv8 detection + centroid tracking on graded clip 01 window.

Draws clean green boxes with class labels (NMS, confirmed tracks only),
plus a PIL-rendered HUD: 'VEHICLES COUNTED: N' (unique tracks).
"""
import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image, ImageDraw, ImageFont

BASE = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_cinematic/build/v2"
SRC = BASE + "/work/eye_graded.mp4"
OUT = BASE + "/work/eye_render.mp4"
MODEL = BASE + "/yolov8n.onnx"

VEHICLES = {1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
CONF = 0.38
GREEN = (0, 230, 118)

FB = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
FR = "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf"
f_count = ImageFont.truetype(FB, 46)
f_sub = ImageFont.truetype(FR, 25)
f_label = ImageFont.truetype(FB, 27)

sess = ort.InferenceSession(MODEL, providers=["CPUExecutionProvider"])
inp_name = sess.get_inputs()[0].name


def detect(frame):
    h, w = frame.shape[:2]
    img = cv2.resize(frame, (640, 640)).astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))[None]
    pred = sess.run(None, {inp_name: img})[0][0].T
    boxes, scores, classes = [], [], []
    for row in pred:
        cs = row[4:]
        c = int(np.argmax(cs))
        s = float(cs[c])
        if s < CONF or c not in VEHICLES:
            continue
        cx, cy, bw, bh = row[0], row[1], row[2], row[3]
        x1 = int((cx - bw / 2) / 640 * w)
        y1 = int((cy - bh / 2) / 640 * h)
        bw2 = int(bw / 640 * w)
        bh2 = int(bh / 640 * h)
        if bw2 < 40 or bh2 < 40:
            continue
        # kill flat false positives hugging the bottom edge
        if y1 + bh2 >= h - 2 and bh2 < 170:
            continue
        boxes.append([x1, y1, bw2, bh2])
        scores.append(s)
        classes.append(c)
    if not boxes:
        return []
    idxs = cv2.dnn.NMSBoxes(boxes, scores, CONF, 0.45)
    if len(idxs) == 0:
        return []
    return [(boxes[int(i)], classes[int(i)]) for i in np.array(idxs).flatten()]


class Track:
    _next = 1

    def __init__(self, box, cls):
        self.id = Track._next
        Track._next += 1
        self.box = np.array(box, dtype=np.float64)
        self.cls = cls
        self.hits = 1
        self.miss = 0

    @property
    def confirmed(self):
        return self.hits >= 3

    def centroid(self):
        return (self.box[0] + self.box[2] / 2, self.box[1] + self.box[3] / 2)


cap = cv2.VideoCapture(SRC)
fps = cap.get(cv2.CAP_PROP_FPS)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
writer = cv2.VideoWriter(OUT, cv2.VideoWriter_fourcc(*"mp4v"), fps, (W, H))

tracks = []
counted = 0
frame_no = 0
while True:
    ok, frame = cap.read()
    if not ok:
        break
    frame_no += 1
    dets = detect(frame)

    # match by centroid distance
    unmatched = list(range(len(dets)))
    for tr in tracks:
        tcx, tcy = tr.centroid()
        best, bestd = -1, 90.0
        for j in unmatched:
            b = dets[j][0]
            dcx, dcy = b[0] + b[2] / 2, b[1] + b[3] / 2
            d = float(np.hypot(dcx - tcx, dcy - tcy))
            if d < bestd:
                bestd, best = d, j
        if best >= 0:
            nb = np.array(dets[best][0], dtype=np.float64)
            tr.box = 0.55 * nb + 0.45 * tr.box  # EMA smoothing
            tr.cls = dets[best][1]
            tr.hits += 1
            tr.miss = 0
            unmatched.remove(best)
        else:
            tr.miss += 1
    new_tracks = []
    for j in unmatched:
        new_tracks.append(Track(dets[j][0], dets[j][1]))
    alive = []
    for tr in tracks + new_tracks:
        if not tr.confirmed and tr.miss > 4:
            continue
        if tr.confirmed and tr.miss > 12:
            continue
        alive.append(tr)
        if tr.confirmed and not hasattr(tr, "_counted"):
            tr._counted = True
            counted += 1
    tracks = alive

    # draw with PIL
    img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    d = ImageDraw.Draw(img, "RGBA")
    for tr in tracks:
        if not tr.confirmed or tr.miss > 3:
            continue
        x, y, bw, bh = [int(v) for v in tr.box]
        d.rectangle([x, y, x + bw, y + bh], outline=GREEN + (255,), width=3)
        label = VEHICLES[tr.cls]
        tw = d.textlength(label, font=f_label)
        ly = max(0, y - 34)
        d.rectangle([x, ly, x + tw + 16, ly + 34], fill=GREEN + (255,))
        d.text((x + 8, ly + 3), label, font=f_label, fill=(8, 10, 8))
    # HUD panel
    d.rectangle([36, 36, 640, 148], fill=(4, 6, 8, 185))
    d.rectangle([36, 36, 640, 148], outline=GREEN + (200,), width=2)
    d.text((58, 54), "VEHICLES COUNTED: ", font=f_count, fill=(240, 240, 240))
    nw = d.textlength("VEHICLES COUNTED: ", font=f_count)
    d.text((58 + nw, 54), str(counted), font=f_count, fill=GREEN)
    d.text((58, 110), "YOLOv8 - LIVE VEHICLE DETECTION", font=f_sub,
           fill=(170, 200, 180))
    d.text((W - 330, H - 52), "CAM 01 - INTERSECTION", font=f_sub,
           fill=(200, 200, 200, 220))
    writer.write(cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR))
    if frame_no % 90 == 0:
        print(f"frame {frame_no}, counted={counted}", flush=True)

cap.release()
writer.release()
print(f"DONE frames={frame_no} counted={counted}")
