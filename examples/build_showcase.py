"""Export identical-kernel evidence and browser Python sources for the showcase."""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import zipfile

from sabz_edge.simulation import SCENARIOS, arrival_stream, simulate

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "showcase/dist"
SOURCES = ("__init__.py", "adaptive.py", "core.py", "cabinet_model.py", "simulation.py")
MODES = ("fixed", "actuated", "adaptive")


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def main():
    DIST.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name in SOURCES:
        source = ROOT / "sabz_edge" / name
        target = DIST / "python/sabz_edge" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    write(DIST / "data/source-manifest.json", hashes)
    for scenario in SCENARIOS:
        for seed in (17, 41, 83):
            stream = arrival_stream(scenario, seed, 360)
            results = {mode: simulate(scenario, seed, 360, mode, stream=stream) for mode in MODES}
            assert len({r["arrival_sha256"] for r in results.values()}) == 1
            write(DIST / f"data/{scenario}-{seed}.json", {"input": "synthetic", "time_basis": "virtual seconds",
                                                       "scenario": scenario, "seed": seed, "source_sha256": hashes, "results": results})
        print("Exported playback:", scenario, flush=True)
    rows = []
    for scenario in SCENARIOS:
        for seed in (41, 83, 119, 211, 307):
            stream = arrival_stream(scenario, seed, 600)
            for mode in MODES:
                result = simulate(scenario, seed, 600, mode, stream=stream, trace=False)
                result.pop("frames")
                rows.append(result)
    summaries = []
    for scenario in SCENARIOS:
        group = {mode: [r for r in rows if r["scenario"] == scenario and r["controller"] == mode] for mode in MODES}
        means = {mode: statistics.mean(r["mean_delay_s"] for r in group[mode]) for mode in MODES}
        summaries.append({"scenario": scenario, "mean_delay_s": means,
                          "seed_stddev_s": {m: statistics.stdev(r["mean_delay_s"] for r in group[m]) for m in MODES},
                          "vs_fixed_pct": 100 * (means["fixed"] - means["adaptive"]) / max(means["fixed"], .001),
                          "vs_actuated_pct": 100 * (means["actuated"] - means["adaptive"]) / max(means["actuated"], .001)})
    report = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "input": "synthetic",
              "duration_s": 600, "seeds": [41, 83, 119, 211, 307], "scenarios": SCENARIOS,
              "source_sha256": hashes, "summary": summaries, "rows": rows,
              "limitations": ["Two through-only movement groups; no turns or pedestrians.",
                              "Point queues and ideal detectors; no collision or braking model.",
                              "Accrued queue delay includes unfinished vehicles; backlog is reported.",
                              "Not a SCATS/SCOOT implementation, field trial, or trained neural model."]}
    write(DIST / "data/benchmark.json", report)
    evidence = ROOT / "validation/adaptive-benchmark.json"
    write(evidence, report)
    with (DIST / "data/benchmark.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    with zipfile.ZipFile(DIST / "data/python-source.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for name in SOURCES:
            archive.write(ROOT / "sabz_edge" / name, f"sabz_edge/{name}")
    for row in summaries:
        print(row, flush=True)


if __name__ == "__main__":
    main()
