"""Local operator dashboard: renders the /v1/metrics snapshot in a terminal.

Reads protected local credentials and stays on this machine; no cloud service
is in the path and tokens are never placed in a browser URL.
"""
import json
import ssl
import sys
import time
import urllib.request

APPROACHES = ("N", "S", "E", "W")


def _cell(value):
    if value is None:
        return "-"
    if isinstance(value, float):
        return str(int(value)) if value == int(value) else f"{value:.2f}"
    return str(value)


def render(snapshot, now=None):
    """Render one /v1/metrics snapshot as terminal text."""
    if not isinstance(snapshot, dict) or "error" in snapshot:
        error = snapshot.get("error", "invalid_snapshot") if isinstance(snapshot, dict) else "invalid_snapshot"
        return f"dashboard unavailable: {error}"
    controller = snapshot.get("controller") or {}
    metrics = snapshot.get("metrics")
    lamps = controller.get("lamps") or {}
    stamp = time.strftime("%H:%M:%S", time.localtime(
        now if now is not None else snapshot.get("now") or time.time()))
    lines = [f"SABZ edge dashboard  {stamp}"]
    lines.append("signal: {stage} phase {phase} elapsed {elapsed}  algorithm {algorithm}".format(
        stage=controller.get("stage", "?"), phase=controller.get("phase", "?"),
        elapsed=_cell(controller.get("elapsed_s")), algorithm=controller.get("algorithm", "?")))
    age = snapshot.get("sensor_age_s")
    age_text = "no feed" if age is None else f"{age:.1f}s"
    freshness = "fresh" if snapshot.get("sensor_fresh") else "STALE"
    loop = "healthy" if snapshot.get("loop_healthy") else "DEGRADED"
    fault = controller.get("fault") or "none"
    preemption = controller.get("preemption") or {}
    preempt_text = (f"ACTIVE {preemption.get('approach')}"
                    if preemption.get("active") else "off")
    lines.append(f"loop: {loop}  sensor: {age_text} {freshness}  "
                 f"fault: {fault}  preemption: {preempt_text}")
    if metrics is None:
        lines.append("no metric feed yet (waiting for /v1/observations or /v1/telemetry)")
    else:
        lines.append(f"feed: seq {metrics.get('sequence')}  "
                     f"healthy {_cell(metrics.get('healthy'))}  "
                     f"conflict_clear {_cell(metrics.get('conflict_clear'))}")
        lines.append("  ap  lamp    count  approach  arrival/s  wait_s  ped")
        for approach in APPROACHES:
            lines.append("  {a}   {lamp:<7} {count:<6} {near:<9} {rate:<10} {wait:<7} {ped}".format(
                a=approach, lamp=lamps.get(approach, "?"),
                count=_cell((metrics.get("counts") or {}).get(approach)),
                near=_cell((metrics.get("approaching") or {}).get(approach)),
                rate=_cell((metrics.get("arrival_rate") or {}).get(approach)),
                wait=_cell((metrics.get("oldest_wait_s") or {}).get(approach)),
                ped=_cell((metrics.get("pedestrian_queue") or {}).get(approach))))
    transitions = snapshot.get("recent_transitions") or []
    if transitions:
        lines.append("recent transitions:")
        for event in transitions[:5]:
            payload = event.get("payload") or {}
            lines.append("  {stage:<8} {phase:<3} {reason}".format(
                stage=payload.get("stage", "?"), phase=payload.get("phase", "?"),
                reason=payload.get("reason", "")))
    alerts = snapshot.get("recent_alerts") or []
    if alerts:
        lines.append("alerts:")
        for event in alerts[:5]:
            payload = event.get("payload") or {}
            detail = " ".join(f"{key}={value}" for key, value in payload.items()
                              if key != "kind")
            lines.append("  {kind:<22} {detail}".format(
                kind=payload.get("kind", event.get("kind", "?")), detail=detail))
    return "\n".join(lines)


def fetch(url, token, cafile=None, timeout=3):
    """Fetch one authenticated /v1/metrics snapshot."""
    handlers = [urllib.request.ProxyHandler({})]
    if url.startswith("https://"):
        handlers.append(urllib.request.HTTPSHandler(
            context=ssl.create_default_context(cafile=cafile)))
    opener = urllib.request.build_opener(*handlers)
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with opener.open(request, timeout=timeout) as response:
        return json.load(response)


def watch(url, token, cafile=None, interval=1.0, out=None, max_frames=None):
    """Refresh the dashboard until interrupted (Ctrl+C)."""
    out = out or sys.stdout
    frames = 0
    try:
        while max_frames is None or frames < max_frames:
            try:
                text = render(fetch(url, token, cafile))
            except Exception as error:  # Keep showing the last failure, not a crash.
                text = f"dashboard unavailable: {error}"
            out.write("\x1b[2J\x1b[H" + text + "\n")
            out.flush()
            frames += 1
            if max_frames is None or frames < max_frames:
                time.sleep(interval)
    except KeyboardInterrupt:
        pass


def main(argv=None):
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True,
                        help="local installation directory holding instance.json")
    parser.add_argument("--interval", type=float, default=1.0,
                        help="refresh period in seconds")
    parser.add_argument("--frames", type=int, default=None,
                        help="stop after this many frames (default: run until Ctrl+C)")
    args = parser.parse_args(argv)
    config = args.directory.resolve() / "instance.json"
    try:
        settings = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise SystemExit(f"cannot read {config}: {error}")
    url = f"https://127.0.0.1:{settings['SABZ_PORT']}/v1/metrics"
    watch(url, settings["SABZ_READER_TOKEN"],
          cafile=settings.get("SABZ_TLS_CERT"),
          interval=args.interval, max_frames=args.frames)


if __name__ == "__main__":
    main()