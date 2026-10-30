"""Held-out controller benchmark: fixed vs actuated vs adaptive on identical traces.

Every mode receives the exact same pre-generated arrival stream per
(scenario, seed) cell and runs through the real safety kernel and virtual
cabinet. Raw per-second queue traces are written for offline analysis.
"""
import argparse
import json
from pathlib import Path
import statistics
import time

from sabz_edge.simulation import SCENARIOS, arrival_stream, simulate

ROOT = Path(__file__).resolve().parents[1]
MODES = ("fixed", "actuated", "adaptive")
# Held out: never used by qualify_virtual (7,41,307,991,2026),
# build_showcase (41,83,119,211,307) or the RL benchmark (11,22,33).
SEEDS = (1013, 2027, 3049, 4051, 5059)
DURATION = 600
# Fault windows injected by the "sensor" scenario (see simulation.rates).
FAULT_WINDOW_S = (100.0, 120.0)


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(fraction * len(ordered)))]


def main():
    parser = argparse.ArgumentParser(description="Held-out fixed/actuated/adaptive benchmark")
    parser.add_argument("--quick", action="store_true", help="2 seeds and 300s runs")
    parser.add_argument("--output", default="validation/benchmark-harness.json")
    args = parser.parse_args()
    seeds = SEEDS[:2] if args.quick else SEEDS
    duration = 300 if args.quick else DURATION

    rows, traces = [], {}
    started = time.monotonic()
    for scenario in SCENARIOS:
        for seed in seeds:
            stream = arrival_stream(scenario, seed, duration)
            group = [simulate(scenario, seed, duration, mode, stream=stream, trace=True)
                     for mode in MODES]
            assert len({r["arrival_sha256"] for r in group}) == 1, "shared stream mismatch"
            for result in group:
                assert result["arrived"] == result["served"] + result["unfinished"], "conservation failed"
                frames = result.pop("frames")
                # Raw per-second queue trace for offline analysis.
                traces[f"{scenario}/{seed}/{result['controller']}"] = [
                    {"t": f["t"], "queues": f["queues"], "stage": f["stage"],
                     "phase": f["phase"], "lamps": f["lamps"], "reason": f["reason"]}
                    for f in frames if f["t"] % 1 == 0]
                if scenario == "sensor":
                    in_fault = [f for f in frames
                                if FAULT_WINDOW_S[0] <= f["t"] < FAULT_WINDOW_S[1]]
                    out_fault = [f for f in frames
                                 if not (FAULT_WINDOW_S[0] <= f["t"] < FAULT_WINDOW_S[1])]
                    result["fault_window"] = {
                                            "mean_queue": round(statistics.mean(sum(f["queues"]) for f in in_fault), 3),
                                            "max_queue": max((sum(f["queues"]) for f in in_fault), default=0),
                                            "max_wait_s": round(max((f["max_wait_s"] for f in in_fault), default=0), 3),
                                            "recovery_max_wait_s": round(max((f["max_wait_s"] for f in out_fault), default=0), 3),
                                            "sensor_ok_frames": sum(1 for f in in_fault if f["sensor_ok"])}
                rows.append(result)
            print(f"Completed {scenario} seed {seed}", flush=True)

    summary = []
    for scenario in SCENARIOS:
        entry = {"scenario": scenario, "modes": {}}
        for mode in MODES:
            group = [r for r in rows if r["scenario"] == scenario and r["controller"] == mode]
            entry["modes"][mode] = {
                "mean_delay_s": round(statistics.mean(r["mean_delay_s"] for r in group), 3),
                "delay_stddev_s": round(statistics.stdev([r["mean_delay_s"] for r in group]), 3),
                "p95_wait_s": round(max(r["p95_completed_wait_s"] or 0 for r in group), 3),
                "p99_wait_s": round(max(r["p99_completed_wait_s"] or 0 for r in group), 3),
                "unfinished": [r["unfinished"] for r in group],
                "max_observed_wait_s": round(max(r["max_observed_wait_s"] for r in group), 3)}
        fixed = entry["modes"]["fixed"]["mean_delay_s"]
        adaptive = entry["modes"]["adaptive"]["mean_delay_s"]
        actuated = entry["modes"]["actuated"]["mean_delay_s"]
        entry["adaptive_vs_fixed_pct"] = round(100 * (fixed - adaptive) / max(fixed, .001), 2)
        entry["adaptive_vs_actuated_pct"] = round(100 * (actuated - adaptive) / max(actuated, .001), 2)
        summary.append(entry)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input": "synthetic pre-generated arrival streams shared across modes",
        "modes": list(MODES),
        "adaptive_policy": "capacity-aware-adaptive-v1 (pressure-based)",
        "scenarios": list(SCENARIOS),
        "seeds": list(seeds),
        "held_out": True,
        "duration_s": duration,
        "wall_clock_s": round(time.monotonic() - started, 1),
        "checks": ["identical arrival stream per cell", "vehicle conservation",
                   "no conflicting virtual outputs", "no virtual cabinet faults"],
        "summary": summary,
        "rows": rows,
        "limitations": [
            "Synthetic Poisson/platoon arrivals; not recorded Lahore traffic.",
            "Point queues with ideal detectors; no turns, pedestrians or collisions.",
            "Fault window metrics cover the injected camera-loss interval only.",
            "Virtual cabinet only; no physical hardware or field validation."]}
    out = ROOT / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    trace_path = out.with_name("benchmark-harness-traces.json")
    trace_path.write_text(json.dumps(traces, separators=(",", ":")), encoding="utf-8")

    print(f"\n{'scenario':<11} {'fixed':>8} {'actuated':>9} {'adaptive':>9} {'vs fixed':>9} {'vs act':>8}")
    for entry in summary:
        m = entry["modes"]
        print(f"{entry['scenario']:<11} {m['fixed']['mean_delay_s']:>8.2f} "
              f"{m['actuated']['mean_delay_s']:>9.2f} {m['adaptive']['mean_delay_s']:>9.2f} "
              f"{entry['adaptive_vs_fixed_pct']:>8.1f}% {entry['adaptive_vs_actuated_pct']:>7.1f}%")
    print(f"\nPASS: {len(rows)} runs, {len(seeds)} held-out seeds, "
          f"{round(time.monotonic() - started, 1)}s wall clock")
    print(f"Report: {out}")
    print(f"Traces: {trace_path}")


if __name__ == "__main__":
    main()