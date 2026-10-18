"""SABZ demo: run scenarios, print results, build charts + animated video."""
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle

from sabz_sim import SCENARIOS, run

OUT = os.path.dirname(os.path.abspath(__file__))
SEEDS = [11, 22, 33, 44, 55]
T = 3600.0


def evaluate():
    rows = []
    for name, (rates, sched, desc) in SCENARIOS.items():
        for ctrl in ("fixed", "sabz"):
            ms = [run(ctrl, rates, schedule=sched, T=T, seed=s) for s in SEEDS]
            agg = {k: float(np.mean([m[k] for m in ms]))
                   for k in ("avg_delay_s", "wasted_green_s", "throughput_per_h",
                             "fuel_wasted_L", "co2_kg", "max_queue", "switches")}
            agg.update(scenario=name, controller=ctrl, desc=desc,
                       vehicles=int(np.mean([m["vehicles"] for m in ms])))
            rows.append(agg)
    return rows


def print_table(rows):
    print(f"{'scenario':<11}{'controller':<10}{'avg_delay':>10}"
          f"{'wasted_grn':>11}{'fuel_L':>8}{'co2_kg':>8}")
    for r in rows:
        print(f"{r['scenario']:<11}{r['controller']:<10}"
              f"{r['avg_delay_s']:>10.1f}{r['wasted_green_s']:>11.0f}"
              f"{r['fuel_wasted_L']:>8.1f}{r['co2_kg']:>8.1f}")
    print()
    for name in SCENARIOS:
        f = next(r for r in rows if r["scenario"] == name and r["controller"] == "fixed")
        s = next(r for r in rows if r["scenario"] == name and r["controller"] == "sabz")
        cut = 100 * (f["avg_delay_s"] - s["avg_delay_s"]) / f["avg_delay_s"]
        wg = 100 * (f["wasted_green_s"] - s["wasted_green_s"]) / max(f["wasted_green_s"], 1)
        print(f"{name}: delay cut {cut:.1f}%, wasted-green cut {wg:.1f}%")


def chart_bars(rows):
    names = list(SCENARIOS)
    x = np.arange(len(names))
    fd = [next(r["avg_delay_s"] for r in rows if r["scenario"] == n and r["controller"] == "fixed") for n in names]
    sd = [next(r["avg_delay_s"] for r in rows if r["scenario"] == n and r["controller"] == "sabz") for n in names]
    fig, ax = plt.subplots(figsize=(10, 5.2))
    w = 0.36
    ax.bar(x - w / 2, fd, w, label="Fixed-time signal", color="#c53030")
    ax.bar(x + w / 2, sd, w, label="SABZ adaptive", color="#276749")
    for i, (a, b) in enumerate(zip(fd, sd)):
        cut = 100 * (a - b) / a
        ax.text(i, max(a, b) + 1.5, f"-{cut:.0f}%", ha="center", fontsize=11, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(["Asymmetric\n(2 vs 50 cars)", "School morning\nrush", "Balanced\nrush hour"])
    ax.set_ylabel("Average delay per vehicle (seconds)")
    ax.set_title("SABZ vs fixed-time signals: average vehicle delay (1-hour simulation, 5 runs)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "chart_delay.png"), dpi=150)
    plt.close(fig)


def chart_queues():
    rates, sched, _ = SCENARIOS["asymmetric"]
    mf = run("fixed", rates, schedule=sched, T=1200.0, seed=11, trace=True)
    ms = run("sabz", rates, schedule=sched, T=1200.0, seed=11, trace=True)
    fig, ax = plt.subplots(figsize=(10, 4.6))
    tf = [p["t"] / 60 for p in mf["trace"]]
    qf = [sum(p["queues"].values()) for p in mf["trace"]]
    qs = [sum(p["queues"].values()) for p in ms["trace"]]
    ax.plot(tf, qf, label="Fixed-time", color="#c53030", lw=1.6)
    ax.plot(tf, qs, label="SABZ adaptive", color="#276749", lw=1.6)
    ax.set_xlabel("Time (minutes)")
    ax.set_ylabel("Vehicles waiting at intersection")
    ax.set_title("Queue build-up: asymmetric demand (same traffic, both controllers)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "chart_queues.png"), dpi=150)
    plt.close(fig)


def draw_panel(ax, frame, title, color):
    ax.set_xlim(-11, 11)
    ax.set_ylim(-11, 11)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.set_title(title, fontsize=14, fontweight="bold", color=color)
    # roads
    ax.add_patch(Rectangle((-11, -1.7), 22, 3.4, color="#4a5568", zorder=1))
    ax.add_patch(Rectangle((-1.7, -11), 3.4, 22, color="#4a5568", zorder=1))
    ax.add_patch(Rectangle((-1.7, -1.7), 3.4, 3.4, color="#2d3748", zorder=2))
    # lane markings
    for x in (-0.05,):
        ax.plot([x, x], [-11, -1.9], color="white", lw=1, ls=(0, (4, 4)), zorder=2)
        ax.plot([x, x], [1.9, 11], color="white", lw=1, ls=(0, (4, 4)), zorder=2)
    ax.plot([-11, -1.9], [-0.05, -0.05], color="white", lw=1, ls=(0, (4, 4)), zorder=2)
    ax.plot([1.9, 11], [-0.05, -0.05], color="white", lw=1, ls=(0, (4, 4)), zorder=2)
    # cars (cap drawn at 12 per approach)
    q = frame["queues"]
    car = "#f6e05e"
    def stack(n, x0, y0, dx, dy):
        for i in range(min(n, 12)):
            ax.add_patch(Rectangle((x0 + i * dx - 0.45, y0 + i * dy - 0.7),
                                   0.9, 1.4, color=car, ec="#744210", zorder=3))
    stack(q["N"], 0.9, 3.2, 0, 1.75)
    stack(q["S"], -0.9, -3.2, 0, -1.75)
    stack(q["E"], 3.2, -0.9, 1.75, 0)
    stack(q["W"], -3.2, 0.9, -1.75, 0)
    # signal light
    ns_green = frame["green"] and frame["phase"] == "NS"
    ew_green = frame["green"] and frame["phase"] == "EW"
    light = "#38a169" if (ns_green or ew_green) else ("#ecc94b" if not frame["green"] else "#e53e3e")
    ax.add_patch(Circle((0, 0), 1.1, color=light, ec="black", zorder=4))
    ax.text(0, 0, frame["phase"], ha="center", va="center", fontsize=9,
            fontweight="bold", zorder=5)
    total_q = sum(q.values())
    avg = frame["delay"] / max(frame["arrived"], 1)
    ax.text(0, -9.6, f"t={frame['t']:.0f}s  waiting={total_q}  served={frame['served']}  "
                      f"avg delay={avg:.1f}s  wasted green={frame['wasted']:.0f}s",
            ha="center", fontsize=10, bbox=dict(boxstyle="round", fc="white", alpha=0.85))


def make_video():
    rates, sched, _ = SCENARIOS["asymmetric"]
    mf = run("fixed", rates, schedule=sched, T=120.0, seed=7, trace=True)
    ms = run("sabz", rates, schedule=sched, T=120.0, seed=7, trace=True)
    frames = os.path.join(OUT, "frames")
    os.makedirs(frames, exist_ok=True)
    n = len(mf["trace"])
    for i in range(n):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(12.8, 7.2))
        fig.suptitle("Same traffic, side by side: fixed-time signal vs SABZ adaptive",
                     fontsize=15, fontweight="bold")
        draw_panel(a1, mf["trace"][i], "FIXED-TIME (25 s green, blind)", "#c53030")
        draw_panel(a2, ms["trace"][i], "SABZ (green follows real demand)", "#276749")
        fig.tight_layout(rect=[0, 0, 1, 0.93])
        fig.savefig(os.path.join(frames, f"f_{i:03d}.png"), dpi=100)
        plt.close(fig)
        if i % 30 == 0:
            print(f"frame {i}/{n}", flush=True)
    mp4 = os.path.join(OUT, "sabz_demo.mp4")
    os.system(f"ffmpeg -y -loglevel error -framerate 6 -i {frames}/f_%03d.png "
              f"-c:v libx264 -pix_fmt yuv420p {mp4}")
    print("video:", mp4)


if __name__ == "__main__":
    rows = evaluate()
    print_table(rows)
    chart_bars(rows)
    chart_queues()
    print("charts saved")
    make_video()
