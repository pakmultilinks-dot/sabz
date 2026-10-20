import time, json
from playwright.sync_api import sync_playwright

BUILD = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_video/build"
URL = "http://localhost:8901/index.html"

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--force-device-scale-factor=1"])
    ctx = browser.new_context(viewport={"width": 1600, "height": 900},
                              record_video_dir=f"{BUILD}/recB",
                              record_video_size={"width": 1600, "height": 900})
    t0 = time.time()
    page = ctx.new_page()
    page.goto(URL)
    # wait for brain
    for _ in range(80):
        r = page.evaluate("() => document.getElementById('decReason').textContent")
        if "loading" not in r:
            break
        time.sleep(0.4)
    print("brain ready at", round(time.time() - t0, 2), flush=True)
    # fps probe
    page.evaluate("""() => { window.__frames = 0; const c = () => { window.__frames++; requestAnimationFrame(c); }; requestAnimationFrame(c); }""")
    time.sleep(3)
    fps = page.evaluate("() => window.__frames") / 3.0
    print("measured fps:", round(fps, 1), flush=True)
    # start battle: reset, set 4x button state, then override tick multiplier for capture
    page.evaluate("() => { resetAll(); setSpeed(4); speed = 10; }")
    t_reset = time.time() - t0
    print("battle start (video t=", round(t_reset, 2), ")", flush=True)
    events = []
    winner_t = None
    last_clock = -1
    deadline = time.time() + 170
    while time.time() < deadline:
        time.sleep(1.0)
        d = page.evaluate("""() => {
          const w = document.getElementById('winner');
          return { clock: document.getElementById('simClock').textContent,
                   winner: w.classList.contains('show'), wtext: w.textContent || '',
                   dL: document.getElementById('dL').textContent,
                   dR: document.getElementById('dR').textContent };
        }""")
        now = time.time() - t0
        sim_s = int(d["clock"].split("+")[1].rstrip("s"))
        if sim_s != last_clock:
            last_clock = sim_s
            events.append({"t": round(now, 2), "sim": sim_s, "dL": d["dL"], "dR": d["dR"]})
        if d["winner"] and winner_t is None:
            winner_t = now
            print("WINNER at video t =", round(now, 2), "|", d["wtext"], flush=True)
            events.append({"t": round(now, 2), "event": "WINNER", "text": d["wtext"]})
        if winner_t and now > winner_t + 8:
            break
        if sim_s >= 210:
            print("sim cap reached", flush=True)
            break
    page.screenshot(path=f"{BUILD}/battle_end2.png")
    ctx.close()
    meta = {"t_reset": t_reset, "winner_t": winner_t, "fps": fps, "events": events}
    with open(f"{BUILD}/recB_meta.json", "w") as f:
        json.dump(meta, f, indent=1)
    print("DONE winner_t:", winner_t, "total rec:", round(time.time() - t0, 1), flush=True)
    browser.close()
