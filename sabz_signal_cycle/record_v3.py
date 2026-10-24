import time
from playwright.sync_api import sync_playwright

LB = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_signal_cycle"
URL = "http://localhost:8951/index_v3.html"
DUR = 95  # record a little past the 93s video, trim in ffmpeg

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1600, "height": 1000},
                        record_video_dir=LB + "/raw_v3",
                        record_video_size={"width": 1600, "height": 1000})
    pg = ctx.new_page()
    pg.goto(URL)
    pg.wait_for_function("window.__ready === true", timeout=15000)
    print("page ready, recording %.0fs" % DUR)
    pg.wait_for_timeout(DUR * 1000)
    video = pg.video
    pg.close()
    ctx.close()
    b.close()
    print("recorded:", video.path())
