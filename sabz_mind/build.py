"""Build sabz_mind/index.html: inline real weights + activations into template."""
import json
import os

import numpy as np

WORK = os.path.dirname(os.path.abspath(__file__))
NET = os.path.join(WORK, "..", "sabz_dqn_best.npz")

d = np.load(NET)
w1 = d["p_W1"].astype(float)
w2 = d["p_W2"].astype(float)
w3 = d["p_W3"].astype(float)

with open(os.path.join(WORK, "mind_data.json")) as f:
    data = json.load(f)

data["weights"] = {
    "w1": [round(float(v), 3) for v in w1.flatten()],
    "w2": [round(float(v), 3) for v in w2.flatten()],
    "w3": [round(float(v), 3) for v in w3.flatten()],
    "m1": float(np.abs(w1).max()),
    "m2": float(np.abs(w2).max()),
    "m3": float(np.abs(w3).max()),
}

with open(os.path.join(WORK, "index.template.html")) as f:
    tpl = f.read()

html = tpl.replace("__MIND_DATA__", json.dumps(data, separators=(",", ":")))
with open(os.path.join(WORK, "index.html"), "w") as f:
    f.write(html)

print("built index.html",
      f"({os.path.getsize(os.path.join(WORK, 'index.html'))/1024:.0f} KB)")
