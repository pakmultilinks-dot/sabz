# Local camera sensor component

This adds an executable camera-to-metric path, separate from the historical
uncalibrated quadrant counter. It is not a validated perception product yet.
No camera has been opened and no trained detector has been run in this work.
There is no approved ONNX vehicle-detector file in the repository.

## Delivered behaviour

- An explicit local device index is required. No default webcam, RTSP source,
  surveillance integration or automatic device scan is used.
- Load an existing operator-approved local ONNX file. A required SHA-256 must
  match the exact bytes passed to the inference engine; no model download occurs.
- Contract: YOLOv8 raw COCO-80 output `[1,84,N]`, 640x640 letterbox input. Other
  detector formats/custom class counts are rejected, not guessed.
- OpenCV DNN classic CPU backend preprocesses/infers. COCO bicycle, car,
  motorcycle, bus and truck classes feed local ground-plane tracking.
- Person detections are tallied per approach as pedestrian_queue demand
  (schema v4) and are never counted as vehicles or tracked. A person in a
  supported road region no longer withdraws health. This does not prove all
  people are detected; model quality remains unmeasured.
- The tracker assigns temporary in-memory IDs; it does not identify faces or
  plates. Matching is greedy and not validated against occlusion or identity swaps.
- A single latest frame is retained in RAM; frames and tracks are not written
  to disk or sent to the edge API. CLI output contains aggregate status/counts.
- Camera data, surveyed calibration and separate independent sensor state must
  all be usable. The latter supplies clearance and receiving-road occupancy.
- Observe-only is the default. `--publish` explicitly connects the existing
  authenticated SDK. Failed/stale sensing withdraws health, never infers clearance.

## Prerequisites

1. A permitted dedicated local camera whose index you have identified.
2. An approved, self-contained ONNX model matching the exact contract. Verify
   provenance, export parameters, licensing and local accuracy separately. A
   hash only pins a selected artifact; it does not establish trust or permission.
3. Surveyed calibration for all four approach regions. They must not overlap.
   `examples/calibration.example.json` is synthetic and not a real calibration.
4. A separate sensor process atomically updating a protected JSON file with:
   `captured_at`, `healthy`, `conflict_clear`, `downstream_counts`,
   `downstream_capacity`. Exactly N/S/E/W maps, counts/capacities bounded by the
   observation contract. No implementation of this physical sensor is supplied.
5. A measured upper bound on exposure-to-host-read age for the actual capture
   path. OpenCV read-return time is NOT exposure time. Do not invent zero latency.

Install optional dependencies in the selected environment:

```powershell
python -m pip install '.[vision]'
```

The development computer used OpenCV 5.0.0 and NumPy 2.4.6. Other allowed package
versions still need qualification on the target. No GPU throughput is claimed.
OpenCV's [DNN API](https://docs.opencv.org/4.13.0/d6/d0f/group__dnn.html) documents
the ONNX/preprocessing operations; [capture documentation](https://docs.opencv.org/4.5.3/d8/dfe/classcv_1_1VideoCapture.html)
describes reading frames, not a guaranteed sensor exposure timestamp.

## Observe-only invocation

The names below are REQUIRED LOCAL ARTIFACTS, not shipped ready-to-use files:

```powershell
python -m sabz_edge.camera_sensor --device 0 --model approved-coco-yolov8.onnx --model-sha256 APPROVED_64_CHARACTER_SHA256 --calibration surveyed-calibration.json --sensor-state independent-sensors.json --capture-age-bound-ms MEASURED_BOUND --seconds 60
```

Replace the device index, hash and measured bound deliberately; there is no
correct universal value. This command opens the explicitly selected camera.
It does not publish control observations. With an authorized working setup,
`--publish --endpoint https://edge.internal:8099 --ca-file private-ca.pem`
enables authenticated observations using `SABZ_CAMERA_TOKEN`. Use the strict
required-metric bench profile. An emulated API endpoint is not a road controller.

Independent sensor records must be no older than 150 ms and no more than 50 ms
future-dated relative to the local clock. The record is checked after inference
and again for expiry before submission. Latest-frame age, inferred processing
time and the supplied capture-age bound share a 150 ms pre-submission budget;
the controller independently enforces its 200 ms metric freshness requirement.
These thresholds can cause frequent withdrawal on a slow computer; they are not
proof of deadline compliance or a site-approved fallback plan.

## Current acceptance evidence and remaining work

Tests exercise tensor shape/numeric rejection, letterbox reversal, duplicate
suppression, person retention, region ambiguity, tracking identity/expiry,
independent-sensor freshness, frame staleness and cleanup. The preprocessing to
metric-measurement test uses synthetic images and FIXTURE NETWORK OUTPUTS. It
checks software plumbing, not actual recognition. The model-hash rejection test
uses a deliberately invalid file and does not execute a trained model.

No precision/recall, motorcycle/occlusion performance, calibration error, real
capture latency, sustained CPU throughput or actual camera/backend behaviour is
established. Blank detections do not prove an unobstructed view. Capture now runs in a separate spawned worker with a bounded shared-memory
frame buffer (maximum 1920x1080 BGR). No frame objects are passed through pickle.
The parent rejects stale/invalid metadata, copies only validated dimensions and
can terminate a blocked worker. Tests inject a worker that ignores shutdown and
verify termination without blocking the parent. The worker is fault containment,
not an OS privilege sandbox; actual driver/device recovery remains unverified. Native inference itself can also block;
the downstream freshness interlock is still necessary.

The new runner is an implemented integration component. It does not close the
commercial-release gates in `COMMERCIAL_READINESS.md`, the missing physical
sensor interface or the ESP32 target/electrical validation requirements.


## Offline labelled-data evaluation

`python -m sabz_edge.detection_eval --dataset labelled-images.jsonl --model approved-coco-yolov8.onnx --model-sha256 APPROVED_SHA256 --requirements reviewed-requirements.json --output new-evaluation-report.json`

This operates on authorized LOCAL images and has no control-output path. Each
JSONL record contains `image` (relative to the dataset directory) and
`annotations` (objects with `class_id` and `bbox`=[x1,y1,x2,y2]). Paths outside
the dataset directory and out-of-image annotations are rejected. COCO classes
0/1/2/3/5/7 are supported. The model and input images are hashed into provenance.
Output is aggregate class precision/recall/F1, vehicle-count error and inference
timing; raw images/boxes are not exported. Existing output files are not replaced.

The requirements JSON must explicitly provide positive `min_images` and
`min_ground_truth_per_class`, plus `min_precision` and `min_recall` maps for
`person`, `bicycle`, `car`, `motorcycle`, `bus`, `truck`. Thresholds must come from
the reviewed requirements, not values chosen to make a demo pass. Missing/empty
classes cannot silently pass. Run separate held-out datasets for lighting,
weather, occlusion and density conditions; aggregate metrics can hide failures.
Label quality, coverage and independence from training still need external review.

The evaluator's matching/acceptance logic has unit tests. No actual labelled
dataset/model evaluation has been run, because neither approved model nor image
annotations is available here. Even a passing dataset report retains
`commercial_ready: false`; hardware, calibration and site acceptance remain.


## Vehicle coverage and dense-traffic regression (2026-10-28)

Suppression is now class-aware: overlapping motorcycle/truck/car predictions
no longer erase each other solely because they overlap. Same-class duplicate
suppression remains enabled. This trades cross-class suppression misses for a
possible cross-class double count; compare both misses and count error on held-out
images before selecting a model. Synthetic regression tests cover all five
vehicle classes, 100 distinct motorcycles, clipped/outside-image boxes, invalid
preprocessing, excessive candidates, invalid geometry and nonfinite output.
These tests exercise decoding, not recognition from real pixels.

COCO coverage is not an all-vehicles guarantee. Rickshaws, Qingqi three-wheelers,
tractors with trailers, animal-drawn carts and unusual commercial vehicles need
explicit local labels and measured recall. Do not silently map an unfamiliar
object to a car or assume an empty detection means an empty road. Custom class
exports are currently rejected by the fixed COCO contract; adding a trained
custom taxonomy requires a versioned model/class manifest and coordinated
decoder, tracker and evaluator changes.

For the next detector qualification, collect authorized local images without
face/plate identification. Split by camera/site and capture session (not adjacent
video frames) to avoid train/test leakage. Include cars, motorcycles, bicycles,
buses, trucks, local vehicle types, pedestrians and empty/background images.
Measure separately: day/night, glare, rain, dust/fog, partial/full occlusion,
dense mixed traffic, distant small vehicles, stationary queues, wrong-way
vehicles and camera obstruction/movement. Record per-class precision/recall,
count error, track fragmentation and missed approach hazards, plus end-to-end
frame age on target hardware. More training epochs or a larger model alone
do not establish improvement. Model optimization/quantization requires the same
held-out comparisons and fresh latency measurements. No trained model or labelled
image dataset is currently supplied, so real detector accuracy remains unmeasured.

Official dataset format/reference: https://docs.ultralytics.com/datasets/detect/
and COCO taxonomy: https://docs.ultralytics.com/datasets/detect/coco/ .
