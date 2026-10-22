#!/usr/bin/env python3
"""Record the CURRENT battle-live demo, full battle view at 4x (DECISION beat, v3).
Stops ~3s after the SABZ WINS banner appears so the segment can end on the banner.
"""
import time, json
from playwright.sync_api import sync_playwright

V3 = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_cinematic/build/v3"
URL = "http://localhost:8942/index.html"

with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(viewport={"width": 1600, "height": 1000},
                        record_video_dir=V3 + "/work/raw_battle2",
                        record_video_size={"width": 1600, "height": 1000})
    pg = ctx.new_page()
    t0 = time.time()
    pg.goto(URL)
    pg.wait_for_timeout(2500)
    # hide website chrome (speed controls + note) for a clean film frame;
    # the winner banner (#winner) must stay visible
    pg.add_style_tag(content=".controls,.note{display:none!important}")
    pg.wait_for_timeout(300)
    try:
        pg.evaluate("setSpeed(4)")
        print("speed 4x set")
    except Exception as e:
        print("setSpeed failed:", e)
    banner_at = None
    deadline = time.time() + 240
    while time.time() < deadline:
        try:
            shown = pg.evaluate("() => { const w = document.getElementById('winner'); return w && w.classList.contains('show') ? w.innerText : ''; }")
        except Exception:
            shown = ""
        if shown and "SABZ WINS" in shown.upper():
            banner_at = time.time() - t0
            print("WINNER BANNER at video t=%.2f : %s" % (banner_at, shown))
            break
        pg.wait_for_timeout(250)
    if banner_at is None:
        print("NO BANNER within deadline")
        pg.wait_for_timeout(2000)
    else:
        pg.wait_for_timeout(3000)
    pg.screenshot(path=V3 + "/work/battle_v3_end.png")
    video = pg.video
    pg.close()
    ctx.close()
    b.close()
    print(json.dumps({"video": video.path(), "banner_at": banner_at, "total": round(time.time() - t0, 2)}))
