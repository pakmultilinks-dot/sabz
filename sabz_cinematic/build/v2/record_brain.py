#!/usr/bin/env python3
"""Record sabz_proper/index.html (real DQN brain panel) for the BRAIN section."""
import time
from playwright.sync_api import sync_playwright

OUT = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_cinematic/build/v2/work"

with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
    ctx = b.new_context(
        viewport={"width": 1920, "height": 1080},
        record_video_dir=OUT,
        record_video_size={"width": 1920, "height": 1080},
    )
    pg = ctx.new_page()
    pg.goto("http://localhost:8931/sabz_proper/index.html")
    pg.wait_for_timeout(2500)
    # verify brain loaded
    try:
        qh = pg.text_content("#qHoldV")
        print("Q(HOLD) at load:", qh)
    except Exception as e:
        print("q read fail:", e)
    pg.screenshot(path=OUT + "/brain_check.png")
    # crank speed for lively decisions
    try:
        pg.click("#sp4")
        print("speed set to 4x")
    except Exception as e:
        print("speed click fail:", e)
        pg.evaluate("setSpeed(4)")
    t0 = time.time()
    last_dec = None
    flips = []
    while time.time() - t0 < 26:
        try:
            dec = pg.text_content("#decText")
            if dec != last_dec:
                flips.append((round(time.time() - t0, 1), dec))
                last_dec = dec
        except Exception:
            pass
        pg.wait_for_timeout(300)
    print("decision flips:", flips)
    pg.screenshot(path=OUT + "/brain_end.png")
    ctx.close()
    b.close()
print("recording done")
