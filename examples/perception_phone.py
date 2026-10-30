"""Track B: run the SABZ perception pipeline on recorded street footage (no hardware).

Feeds video frames through the production YOLOv8n ONNX detector, RoadTracker,
and MetricProducer (via sensor_ingest.process_frame) exactly as the live
camera sensor would, then writes a JSON quality report.

Usage:
    python examples/perception_phone.py --video path/to/street.mp4 \
        --calibration validation/calibration-cinematic-topdown.json \
        --model yolov8n.onnx --output validation/perception-phone-report.json
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2  # noqa: E402
from sabz_edge.sensor_ingest import producer_from_file, process_frame  # noqa: E402
from sabz_edge.vision import RoadTracker, YoloOnnx  # noqa: E402

DOWNSTREAM_CAPACITY = 10
CAPTURED_AT_BASE = 1_000_000  # synthetic epoch; offline run has no wall clock contract
DEFAULT_SHA256 = "b5c05c6cc1b6a012fd94a109b7f977610f62b0138077ee932d16c5e31b5ed0cc"


def run(video_path, calibration_path, model_path, output_path, max_frames=None, stride=1,
        expected_sha256=DEFAULT_SHA256):
    producer = producer_from_file(calibration_path)
    detector = YoloOnnx(model_path, expected_sha256)
    tracker = RoadTracker(producer.calibrations)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise SystemExit(f"Cannot open video: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    frames_processed = 0
    frames_healthy = 0
    frames_unhealthy = 0
    frames_error = 0
    detections_seen = 0
    tracks_seen = 0
    errors = {}
    per_approach = {a: {"frames_with_counts": 0, "max_count": 0, "max_approaching": 0,
                        "arrivals": 0} for a in "NSEW"}
    last_state = None
    t_start = time.perf_counter()

    frame_index = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame_index += 1
        if frame_index % stride:
            continue
        if max_frames is not None and frames_processed >= max_frames:
            break

        frame_time_s = frame_index / fps
        try:
            boxes = detector.detect(frame)
            detections_seen += len(boxes)
            tracked, pedestrians = tracker.update(boxes, now=frame_time_s)
            tracks_seen += len(tracked)
            packet = {
                "frame_time_s": frame_time_s,
                "captured_at": CAPTURED_AT_BASE + frame_time_s,
                "detections": [
                    {"track_id": d.track_id, "approach": d.approach,
                     "pixel_x": d.pixel_x, "pixel_y": d.pixel_y,
                     "vehicle_class": d.vehicle_class}
                    for d in tracked
                ],
                "conflict_clear": True,
                "downstream_counts": dict.fromkeys("NSEW", 0),
                "downstream_capacity": dict.fromkeys("NSEW", DOWNSTREAM_CAPACITY),
                "sensors_healthy": True,
                "pedestrian_queue": pedestrians,
            }
            state = process_frame(producer, packet)
        except (ValueError, OSError, RuntimeError) as exc:
            # Mirror camera_sensor.py: withdraw health, keep going, never
            # silently retain a previous healthy measurement.
            frames_error += 1
            key = type(exc).__name__ + ": " + str(exc)[:120]
            errors[key] = errors.get(key, 0) + 1
            frames_unhealthy += 1
            continue

        frames_processed += 1
        last_state = state
        if state["healthy"]:
            frames_healthy += 1
        else:
            frames_unhealthy += 1
        for approach in "NSEW":
            counts = state["traffic_state"]["downstream_counts"][approach]
            approaching = state["traffic_state"]["approaching"][approach]
            if counts:
                per_approach[approach]["frames_with_counts"] += 1
            per_approach[approach]["max_count"] = max(per_approach[approach]["max_count"], counts)
            per_approach[approach]["max_approaching"] = max(
                per_approach[approach]["max_approaching"], approaching)

    cap.release()
    elapsed = time.perf_counter() - t_start

    report = {
        "video": str(video_path),
        "calibration": str(calibration_path),
        "model": str(model_path),
        "footage_type": "rendered synthetic stand-in (not phone footage)",
        "frames_total": total,
        "frames_sampled_stride": stride,
        "frames_processed": frames_processed,
        "frames_healthy": frames_healthy,
        "frames_unhealthy": frames_unhealthy,
        "frames_error": frames_error,
        "detections_seen": detections_seen,
        "tracks_seen": tracks_seen,
        "elapsed_s": round(elapsed, 2),
        "fps_effective": round(frames_processed / elapsed, 2) if elapsed else None,
        "errors": errors,
        "per_approach": per_approach,
        "last_state": last_state,
    }
    Path(output_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "last_state"}, indent=2))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True)
    parser.add_argument("--calibration", required=True)
    parser.add_argument("--model", default="yolov8n.onnx")
    parser.add_argument("--sha256", default=DEFAULT_SHA256,
                            help="Expected sha256 of the ONNX model (integrity check)")
    parser.add_argument("--output", default="validation/perception-phone-report.json")
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--stride", type=int, default=1,
                            help="Process every Nth frame (detector is ~200ms/frame on CPU)")
    args = parser.parse_args()
    run(args.video, args.calibration, args.model, args.output,
        max_frames=args.max_frames, stride=args.stride, expected_sha256=args.sha256)


if __name__ == "__main__":
    main()
