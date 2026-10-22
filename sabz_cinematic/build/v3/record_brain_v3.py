#!/usr/bin/env python3
"""Record the CURRENT battle-live demo focused on the SABZ AI panel (BRAIN beat, v3).
Stacked layout (viewport 1080 wide), other chrome + FIXED panel hidden, 4x speed.
Logs every DQN decision flip so an 18s window containing a SWITCH can be chosen.
"""
import time, json
from playwright.sync_api import sync_playwright

V3 = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_cinematic/build/v3"
URL = "http://localhost:8942/index.html"
CSS = """
nav,.chips,.titlerow,#winner,.controls,.note{display:none!important}
#panelL{display:none!important}
"""

with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(viewport={"width": 1080, "height": 1000},
                        record_video_dir=V3 + "/work/raw_brain",
                        record_video_size={"width": 1080, "height": 1000})
    pg = ctx.new_page()
    t0 = time.time()
    pg.goto(URL)
    pg.wait_for_timeout(2500)
    pg.add_style_tag(content=CSS)
    pg.wait_for_timeout(400)
    try:
        pg.evaluate("setSpeed(4)")
        print("speed 4x set")
    except Exception as e:
        print("setSpeed failed:", e)
    try:
        print("decText at start:", pg.text_content("#decText"))
    except Exception as e:
        print("decText read fail:", e)
    flips = []
    last_dec = None
    t_start = time.time()
    while time.time() - t_start < 40:
        try:
            dec = pg.text_content("#decText")
            if dec != last_dec:
                flips.append([round(time.time() - t0, 2), dec])
                last_dec = dec
        except Exception:
            pass
        pg.wait_for_timeout(200)
    pg.screenshot(path=V3 + "/work/brain_v3_end.png")
    video = pg.video
    pg.close()
    ctx.close()
    b.close()
    print(json.dumps({"video": video.path(), "flips": flips, "total": round(time.time() - t0, 2)}))
