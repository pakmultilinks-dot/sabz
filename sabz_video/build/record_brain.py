import time, json
from playwright.sync_api import sync_playwright

BUILD = "/home/hatch/workspace/goals/ai-championship-adaptive-traffic-signals/sabz_video/build"
URL = "http://localhost:8901/index.html"

FRAME_JS = """() => {
  const ov = document.createElement('div');
  ov.id = 'framingOverlay';
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(3,6,9,0.92);z-index:40;';
  document.body.appendChild(ov);
  const st = document.createElement('style');
  st.textContent = `
    .brain h2{font-size:26px !important; letter-spacing:4px !important;}
    .brain .arch{font-size:17px !important;}
    .layer .n{font-size:34px !important;} .layer .t{font-size:11px !important;}
    .qrow .qh{font-size:17px !important;} .qbar{height:22px !important;}
    .decision .d{font-size:40px !important;} .decision .r{font-size:15px !important;}
    .feats h3{font-size:13px !important;} .feat .fv{font-size:22px !important;} .feat .fl{font-size:10px !important;}
    body{overflow:hidden !important;}`;
  document.head.appendChild(st);
  const b = document.querySelector('.brain');
  b.style.cssText += ';position:fixed;z-index:50;left:50%;top:50%;transform:translate(-50%,-50%);width:1200px;background:#0b0f14;border:1px solid rgba(0,230,118,.45);border-radius:18px;padding:36px 44px;margin:0;box-shadow:0 30px 90px rgba(0,0,0,.65);';
}"""

with sync_playwright() as p:
    browser = p.chromium.launch(args=["--force-device-scale-factor=1"])
    ctx = browser.new_context(viewport={"width": 1600, "height": 900},
                              record_video_dir=f"{BUILD}/recC",
                              record_video_size={"width": 1600, "height": 900})
    t0 = time.time()
    page = ctx.new_page()
    page.goto(URL)
    for _ in range(80):
        r = page.evaluate("() => document.getElementById('decReason').textContent")
        if "loading" not in r:
            break
        time.sleep(0.4)
    print("brain ready at", round(time.time() - t0, 2), flush=True)
    page.evaluate("() => { setSpeed(2); speed = 5; }")
    time.sleep(6)  # let traffic build
    page.evaluate(FRAME_JS)
    t_frame = time.time() - t0
    print("framing applied at video t =", round(t_frame, 2), flush=True)
    page.screenshot(path=f"{BUILD}/brain_framed_check.png")
    # monitor decisions for variety
    decisions = []
    last = None
    end = time.time() + 40
    while time.time() < end:
        time.sleep(0.7)
        d = page.evaluate("""() => ({ dec: document.getElementById('decText').textContent,
                                      qh: document.getElementById('qHoldV').textContent,
                                      qs: document.getElementById('qSwitchV').textContent })""")
        if d["dec"] != last:
            decisions.append({"t": round(time.time() - t0, 2), **d})
            last = d["dec"]
            print("decision ->", d, "at", round(time.time() - t0, 1), flush=True)
    page.screenshot(path=f"{BUILD}/brain_framed_end.png")
    ctx.close()
    with open(f"{BUILD}/recC_meta.json", "w") as f:
        json.dump({"t_frame": t_frame, "decisions": decisions}, f, indent=1)
    print("DONE, decision changes:", len(decisions), flush=True)
    browser.close()
