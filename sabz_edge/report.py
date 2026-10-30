"""Historical traffic report over the local audit journal (no cloud)."""
import argparse
import json
import sqlite3
import time

APPROACHES = "NSEW"
VEHICLE_CLASSES = ("car", "motorcycle", "bicycle", "bus", "truck")
WINDOW_S = 3600  # peak-hour window for foot-traffic analytics
# Rough idle CO2 rates (g/s) used for emission estimates; estimates only.
IDLE_EMISSION_G_PER_S = {"car": 0.56, "motorcycle": 0.12, "bicycle": 0.0,
                         "bus": 2.9, "truck": 3.5}
IDLE_GAP_CAP_S = 60  # ignore journal gaps longer than this when idling


def _ped_total(data):
    """Pedestrians summed across approaches for one observation payload."""
    peds = data.get("pedestrian_queue")
    if isinstance(peds, dict):
        peds = [peds.get(approach) for approach in APPROACHES]
    if not isinstance(peds, (list, tuple)) or len(peds) != len(APPROACHES):
        return 0
    return sum(value for value in peds
               if isinstance(value, (int, float)) and not isinstance(value, bool)
               and value >= 0)


def load(path, since=None):
    """Return (at, kind, payload) events at or after `since`, oldest first."""
    db = sqlite3.connect(path)
    try:
        rows = db.execute(
            "SELECT at, kind, payload FROM events WHERE (? IS NULL OR at >= ?) ORDER BY at",
            (since, since)).fetchall()
    finally:
        db.close()
    events = []
    for at, kind, payload in rows:
        try:
            data = json.loads(payload)
        except (ValueError, TypeError):
            continue  # skip corrupt journal rows rather than fail the report
        if isinstance(data, dict):
            events.append((at, kind, data))
    return events


def summarize(events, now=None):
    """Aggregate events into a historical summary dict."""
    now = time.time() if now is None else now
    summary = {
        "window": {"first_at": None, "last_at": None, "span_s": 0.0},
        "totals": {"observations": 0, "transitions": 0, "preemptions": 0},
        "approaches": {a: {"observations": 0, "vehicles": 0, "avg_vehicles": 0.0,
                           "preemptions": 0} for a in APPROACHES},
        "max_wait_s": None,
        "max_pedestrian_queue": None,
        "pedestrians": {a: {"observations": 0, "pedestrians": 0, "avg_pedestrians": 0.0,
                            "max_pedestrians": 0} for a in APPROACHES},
        "peak_hour": {"first_at": None, "last_at": None, "pedestrians": 0},
        "classes": {name: {"vehicles": 0} for name in VEHICLE_CLASSES},
        "class_observations": 0,
        "approach_classes": {a: {name: 0 for name in VEHICLE_CLASSES}
                             for a in APPROACHES},
        "stage_dwell_s": {},
        "transition_reasons": {},
        "idling": {"vehicle_s": {name: 0.0 for name in VEHICLE_CLASSES},
                   "emissions_g": {name: 0.0 for name in VEHICLE_CLASSES},
                   "observations": 0, "queue_vehicle_s": 0.0,
                   "total_vehicle_s": 0.0, "total_emissions_g": 0.0},
    }
    previous_transition_at = None
    previous_observation_at = None
    for at, kind, data in events:
        if summary["window"]["first_at"] is None:
            summary["window"]["first_at"] = at
        summary["window"]["last_at"] = at
        if kind == "observation":
            summary["totals"]["observations"] += 1
            gap = 0.0
            stamp = data.get("captured_at")
            if not isinstance(stamp, (int, float)) or isinstance(stamp, bool):
                stamp = at
            if previous_observation_at is not None:
                gap = max(0.0, min(stamp - previous_observation_at, IDLE_GAP_CAP_S))
            previous_observation_at = stamp
            counts_total = 0
            counts = data.get("counts")
            if isinstance(counts, dict):
                counts = [counts.get(approach) for approach in APPROACHES]
            if isinstance(counts, (list, tuple)) and len(counts) == len(APPROACHES):
                for approach, value in zip(APPROACHES, counts):
                    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
                        bucket = summary["approaches"][approach]
                        bucket["observations"] += 1
                        bucket["vehicles"] += value
                        counts_total += value
            wait = data.get("oldest_wait_s")
            if isinstance(wait, (int, float)) and not isinstance(wait, bool) and wait >= 0:
                current = summary["max_wait_s"]
                summary["max_wait_s"] = wait if current is None else max(current, wait)
            ped = data.get("pedestrian_queue")
            if type(ped) is int and ped >= 0:
                current = summary["max_pedestrian_queue"]
                summary["max_pedestrian_queue"] = ped if current is None else max(current, ped)
            peds = [ped.get(approach) for approach in APPROACHES] if isinstance(ped, dict) else ped
            if isinstance(peds, (list, tuple)) and len(peds) == len(APPROACHES):
                for approach, value in zip(APPROACHES, peds):
                    if (isinstance(value, (int, float)) and not isinstance(value, bool)
                            and value >= 0):
                        bucket = summary["pedestrians"][approach]
                        bucket["observations"] += 1
                        bucket["pedestrians"] += value
                        bucket["max_pedestrians"] = max(bucket["max_pedestrians"], value)
                        current = summary["max_pedestrian_queue"]
                        summary["max_pedestrian_queue"] = (
                            value if current is None else max(current, value))
            breakdown = data.get("class_counts")
            if isinstance(breakdown, dict) and set(breakdown) == set(APPROACHES):
                summary["class_observations"] += 1
                if gap:
                    summary["idling"]["observations"] += 1
                for approach in APPROACHES:
                    classes = breakdown.get(approach)
                    if not isinstance(classes, dict):
                        continue
                    for name in VEHICLE_CLASSES:
                        value = classes.get(name)
                        if (isinstance(value, (int, float)) and not isinstance(value, bool)
                                and value >= 0):
                            summary["classes"][name]["vehicles"] += value
                            summary["approach_classes"][approach][name] += value
                            if gap:
                                summary["idling"]["vehicle_s"][name] += value * gap
            elif gap and counts_total:
                # No class data: track idle vehicle-seconds without an emission
                # estimate (the class mix is unknown).
                summary["idling"]["queue_vehicle_s"] += counts_total * gap
        elif kind == "transition_intent":
            summary["totals"]["transitions"] += 1
            if previous_transition_at is not None:
                stage = data.get("stage")
                if isinstance(stage, str):
                    dwell = summary["stage_dwell_s"]
                    dwell[stage] = dwell.get(stage, 0.0) + (at - previous_transition_at)
            previous_transition_at = at
            reason = data.get("reason")
            if isinstance(reason, str):
                reasons = summary["transition_reasons"]
                reasons[reason] = reasons.get(reason, 0) + 1
        elif kind == "preemption_requested":
            summary["totals"]["preemptions"] += 1
            approach = data.get("approach")
            if approach in summary["approaches"]:
                summary["approaches"][approach]["preemptions"] += 1
    idling = summary["idling"]
    for name in VEHICLE_CLASSES:
        idling["emissions_g"][name] = round(
            idling["vehicle_s"][name] * IDLE_EMISSION_G_PER_S[name], 3)
    idling["queue_vehicle_s"] = round(idling["queue_vehicle_s"], 3)
    idling["total_vehicle_s"] = round(sum(idling["vehicle_s"].values()), 3)
    idling["total_emissions_g"] = round(sum(idling["emissions_g"].values()), 3)
    for bucket in summary["approaches"].values():
        if bucket["observations"]:
            bucket["avg_vehicles"] = round(bucket["vehicles"] / bucket["observations"], 2)
    for bucket in summary["pedestrians"].values():
        if bucket["observations"]:
            bucket["avg_pedestrians"] = round(bucket["pedestrians"] / bucket["observations"], 2)
    window = summary["window"]
    if window["first_at"] is not None:
        window["span_s"] = round(window["last_at"] - window["first_at"], 3)
        # Peak-hour foot traffic: densest rolling WINDOW_S slice of observations.
        observations = [(at, _ped_total(data)) for at, kind, data in events
                        if kind == "observation"]
        start, running = 0, 0
        peak = summary["peak_hour"]
        for end, (at, total) in enumerate(observations):
            running += total
            while observations[start][0] <= at - WINDOW_S:
                running -= observations[start][1]
                start += 1
            if peak["first_at"] is None or running > peak["pedestrians"]:
                peak.update(first_at=observations[start][0], last_at=at,
                            pedestrians=running)
    return summary


def render(summary):
    """Terminal text for a summary produced by summarize()."""
    window = summary["window"]
    if window["first_at"] is None:
        return "SABZ report: no events recorded in this window."
    stamp = lambda at: time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(at))
    totals = summary["totals"]
    lines = [
        "SABZ historical report",
        f"window: {stamp(window['first_at'])} -> {stamp(window['last_at'])}"
        f"  ({window['span_s']:.1f}s)",
        f"events: {totals['observations']} observations, "
        f"{totals['transitions']} transitions, {totals['preemptions']} preemptions",
        "max wait: "
                + (f"{summary['max_wait_s']}s" if summary["max_wait_s"] is not None else "n/a")
                + "   max pedestrian queue: "
                + (str(summary["max_pedestrian_queue"])
                   if summary["max_pedestrian_queue"] is not None else "n/a"),
        "  ap  obs  vehicles  avg/obs  preempts",
    ]
    for approach in APPROACHES:
        bucket = summary["approaches"][approach]
        lines.append(f"  {approach}   {bucket['observations']:>3}  "
                     f"{bucket['vehicles']:>8}  {bucket['avg_vehicles']:>7}  "
                     f"{bucket['preemptions']:>8}")
    lines.append("  ap  obs   peds  avg/obs  max")
    for approach in APPROACHES:
        bucket = summary["pedestrians"][approach]
        lines.append(f"  {approach}   {bucket['observations']:>3}  "
                     f"{bucket['pedestrians']:>5}  {bucket['avg_pedestrians']:>7}  "
                     f"{bucket['max_pedestrians']:>3}")
    if summary.get("class_observations"):
        lines.append("  stopped vehicles by class (obs with class data: "
                     f"{summary['class_observations']})")
        lines.append(f"  {'class':<10}" + "".join(f"{a:>5}" for a in APPROACHES)
                     + f"{'total':>7}")
        for name in VEHICLE_CLASSES:
            row = [summary["approach_classes"][a][name] for a in APPROACHES]
            lines.append(f"  {name:<10}" + "".join(f"{v:>5}" for v in row)
                         + f"{sum(row):>7}")
    idling = summary["idling"]
    if idling["total_vehicle_s"] > 0:
        lines.append("idling & CO2 estimate (rough idle factors):")
        lines.append(f"  {'class':<10}{'veh-s':>10}{'CO2 g':>10}")
        for name in VEHICLE_CLASSES:
            lines.append(f"  {name:<10}{idling['vehicle_s'][name]:>10.1f}"
                         f"{idling['emissions_g'][name]:>10.1f}")
        lines.append(f"  {'total':<10}{idling['total_vehicle_s']:>10.1f}"
                     f"{idling['total_emissions_g']:>10.1f}")
    if idling["queue_vehicle_s"] > 0:
        lines.append(f"unclassified stopped-vehicle idle: "
                     f"{idling['queue_vehicle_s']:.1f} veh-s (no class data)")
    peak = summary["peak_hour"]
    if peak["first_at"] is not None:
        lines.append(f"peak hour foot traffic: {peak['pedestrians']} peds  "
                     f"{stamp(peak['first_at'])} -> {stamp(peak['last_at'])}")
    if summary["stage_dwell_s"]:
        lines.append("stage dwell:")
        for stage, seconds in sorted(summary["stage_dwell_s"].items()):
            lines.append(f"  {stage}: {seconds:.1f}s")
    if summary["transition_reasons"]:
        lines.append("transition reasons:")
        for reason, count in sorted(summary["transition_reasons"].items(),
                                    key=lambda item: (-item[1], item[0])):
            lines.append(f"  {reason}: {count}")
    return "\n".join(lines)


def parse_since(text):
    """Parse a duration like 90s, 30m, 24h, 7d into an absolute epoch, or None."""
    if text in (None, "", "0", "all"):
        return None
    unit = text[-1]
    amount = float(text[:-1]) if unit in "smhd" else float(text)
    factor = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit, 1)
    return time.time() - amount * factor


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True,
                        help="edge sqlite journal (e.g. data/local-installation/edge.sqlite3)")
    parser.add_argument("--since", default="all",
                        help="window like 90s, 30m, 24h, 7d, or all (default)")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of text")
    args = parser.parse_args(argv)
    summary = summarize(load(args.database, parse_since(args.since)))
    if args.json:
        print(json.dumps(summary, sort_keys=True))
    else:
        print(render(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())