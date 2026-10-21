import time, json
from playwright.sync_api import sync_playwright

LB = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_cinematic/loop_build"
URL = "http://localhost:8941/index.html"

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1600, "height": 1000},
                        record_video_dir=LB + "/raw2",
                        record_video_size={"width": 1600, "height": 1000})
    pg = ctx.new_page()
    t0 = time.time()
    pg.goto(URL)
    pg.wait_for_timeout(2500)
    try:
        pg.evaluate("setSpeed(4)")
        print("speed 4x set")
    except Exception as e:
        print("setSpeed failed:", e)
    banner_at = None
    deadline = time.time() + 150
    txt = ""
    while time.time() < deadline:
        try:
            txt = pg.evaluate("document.body.innerText")
        except Exception:
            txt = ""
        if "SABZ WINS" in txt.upper():
            banner_at = time.time() - t0
            print("WINNER BANNER at video t=%.1f" % banner_at)
            break
        pg.wait_for_timeout(700)
    if banner_at is None:
        print("NO BANNER; sample:", txt[:400])
        pg.wait_for_timeout(2000)
    else:
        pg.wait_for_timeout(3500)
    total = time.time() - t0
    video = pg.video
    pg.close()
    ctx.close()
    b.close()
    print(json.dumps({"video": video.path(), "banner_at": banner_at, "total": total}))
