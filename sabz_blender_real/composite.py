"""SABZ Blender Real - Composite animation with AI overlays.
Builds 20s cinematic video from hero background + animated vehicles + AI.
"""
import cv2
import numpy as np
import os, sys, math, random

random.seed(123)

WORK = os.path.expanduser("~/workspace/goals/ai-championship-adaptive-traffic-signals")
OUT_DIR = os.path.join(WORK, "sabz_blender_real")
BG_PATH = os.path.join(OUT_DIR, "hero_bg_0001.png")

# Load brain for real decisions
sys.path.insert(0, WORK)
from sabz_rl import load_net
net = load_net(os.path.join(WORK, "sabz_dqn_best.npz"))
print("Brain loaded")

# Load background
bg = cv2.imread(BG_PATH)
if bg is None:
    raise FileNotFoundError(f"Background not found: {BG_PATH}")
BH, BW = bg.shape[:2]
print(f"Background: {BW}x{BH}")

# Output: 1280x720, 30fps, 20s = 600 frames
OW, OH = 1280, 720
FPS = 30
DURATION = 20
N_FRAMES = FPS * DURATION

# Vehicle definitions (stylized top-down, matching warm aesthetic)
# Each: (type, color, size_w, size_h, lane, direction, speed, start_offset)
VEHICLES = [
    # East-west road, north lane (y~290 in 720p), moving +x
    ('car', (220, 220, 225), 64, 30, 'ew_n', 1, 2.2, 0),
    ('rickshaw', (30, 30, 35), 42, 24, 'ew_n', 1, 1.8, 300),
    ('car', (180, 60, 50), 64, 30, 'ew_n', 1, 2.0, 600),
    ('bike', (80, 80, 85), 30, 14, 'ew_n', 1, 2.8, 450),
    # East-west road, south lane, moving -x
    ('car', (50, 90, 160), 64, 30, 'ew_s', -1, 2.1, 200),
    ('rickshaw', (30, 30, 35), 42, 24, 'ew_s', -1, 1.7, 500),
    ('car', (200, 200, 205), 64, 30, 'ew_s', -1, 2.3, 700),
    ('bike', (120, 100, 80), 30, 14, 'ew_s', -1, 2.9, 100),
    # North-south road, east lane, moving +y
    ('car', (60, 140, 60), 30, 64, 'ns_e', 1, 2.0, 150),
    ('rickshaw', (30, 30, 35), 24, 42, 'ns_e', 1, 1.6, 550),
    ('car', (210, 210, 215), 30, 64, 'ns_e', 1, 2.2, 400),
    # North-south road, west lane, moving -y
    ('car', (160, 50, 40), 30, 64, 'ns_w', -1, 2.1, 350),
    ('bike', (90, 90, 95), 14, 30, 'ns_w', -1, 2.7, 600),
    ('rickshaw', (30, 30, 35), 24, 42, 'ns_w', -1, 1.8, 250),
]

# Lane positions in output coordinates (tuned to background)
LANES = {
    'ew_n': 295,  # y for north lane of EW road
    'ew_s': 345,  # y for south lane
    'ns_e': 665,  # x for east lane of NS road
    'ns_w': 615,  # x for west lane
}

def draw_vehicle(img, vtype, color, cx, cy, w, h, angle=0):
    """Draw stylized top-down vehicle with soft shadow."""
    # Shadow
    shadow = np.zeros_like(img)
    cv2.ellipse(shadow, (int(cx+3), int(cy+4)), (w//2, h//2), angle, 0, 360, (0,0,0), -1)
    shadow = cv2.GaussianBlur(shadow, (9, 9), 0)
    img = cv2.addWeighted(img, 1.0, shadow, 0.35, 0)
    
    # Body
    if vtype == 'car':
        # Main body (rounded)
        cv2.ellipse(img, (int(cx), int(cy)), (w//2, h//2), angle, 0, 360, color, -1)
        # Windshield (darker, front)
        wx = cx + math.cos(math.radians(angle)) * w * 0.18
        wy = cy + math.sin(math.radians(angle)) * w * 0.18
        cv2.ellipse(img, (int(wx), int(wy)), (w//4, h//3), angle, 0, 360, (40, 45, 55), -1)
        # Roof
        cv2.ellipse(img, (int(cx), int(cy)), (w//3, h//2 - 2), angle, 0, 360, 
                   tuple(min(255, c+20) for c in color), -1)
    elif vtype == 'rickshaw':
        # Body (black)
        cv2.ellipse(img, (int(cx), int(cy)), (w//2, h//2), angle, 0, 360, (25, 25, 30), -1)
        # Yellow front
        fx = cx + math.cos(math.radians(angle)) * w * 0.28
        fy = cy + math.sin(math.radians(angle)) * w * 0.28
        cv2.ellipse(img, (int(fx), int(fy)), (w//5, h//2 - 1), angle, 0, 360, (15, 165, 215), -1)
        # Canopy
        cv2.ellipse(img, (int(cx), int(cy)), (w//3, h//2 - 1), angle, 0, 360, (35, 35, 40), -1)
    elif vtype == 'bike':
        # Thin body
        cv2.ellipse(img, (int(cx), int(cy)), (w//2, h//2), angle, 0, 360, color, -1)
        # Rider (circle)
        cv2.circle(img, (int(cx), int(cy)), h//2 + 1, (100, 75, 60), -1)
    
    return img

def get_vehicle_pos(v, frame):
    """Calculate vehicle position at frame."""
    vtype, color, w, h, lane, direction, speed, offset = v
    # Position along path (0 to OW or OH, wrapping)
    if lane in ['ew_n', 'ew_s']:
        # Moving along x
        total_dist = OW + 200
        x = ((offset + frame * speed * direction) % total_dist) - 100
        if direction < 0:
            x = OW + 100 - ((offset + frame * speed) % total_dist)
        y = LANES[lane] + random.uniform(-2, 2)  # slight lane wobble
        angle = 0 if direction > 0 else 180
    else:
        # Moving along y
        total_dist = OH + 200
        y = ((offset + frame * speed * direction) % total_dist) - 100
        if direction < 0:
            y = OH + 100 - ((offset + frame * speed) % total_dist)
        x = LANES[lane] + random.uniform(-2, 2)
        angle = 90 if direction > 0 else 270
    return x, y, angle, w, h

# Brain state
phase = 0  # 0=EW green, 1=NS green
green_elapsed = 0
switches = 0
brain_history = []

def brain_decision(frame, counts):
    """Get DQN decision every 30 frames."""
    global phase, green_elapsed, switches
    if frame % 30 != 0:
        return None
    # Build 18-dim state from counts
    s = np.zeros(18, dtype=np.float32)
    # Distribute counts
    total = sum(counts.values())
    s[0] = counts.get('ew', 0) / 10.0
    s[1] = counts.get('ns', 0) / 10.0
    s[4] = min(total / 20.0, 1.0)
    s[4 + phase] = 1.0
    s[6] = min(green_elapsed / 60.0, 1.0)
    for i in range(4):
        s[7+i] = 0.2
        s[11+i] = 0.1 if i != phase else 0.0
    s[15] = 0.2; s[16] = 0.1; s[17] = 1.0
    
    q_vals, _ = net.forward(s)
    q_vals = q_vals.flatten()
    action = int(np.argmax(q_vals))
    
    if action == 1 and green_elapsed >= 5:
        phase = 1 - phase
        green_elapsed = 0
        switches += 1
        decision = 'SWITCH'
    else:
        decision = 'HOLD'
        green_elapsed += 1
    
    result = {
        'q_hold': float(q_vals[0]),
        'q_switch': float(q_vals[1]),
        'decision': decision,
        'phase': phase,
    }
    brain_history.append((frame, result))
    return result

# Video writer
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out_path = os.path.join(OUT_DIR, 'sabz_real_blender.mp4')
out = cv2.VideoWriter(out_path, fourcc, FPS, (OW, OH))
print(f"Writing to {out_path}")

# Fonts
font = cv2.FONT_HERSHEY_SIMPLEX
font_big = cv2.FONT_HERSHEY_DUPLEX

# Pre-compute camera drift (subtle Ken Burns)
# Zoom from 1.0 to 1.08, pan slightly
for frame in range(N_FRAMES):
    # Camera drift: slow zoom in + slight pan
    progress = frame / N_FRAMES
    zoom = 1.0 + progress * 0.08
    # Crop region from background (which is 1280x720, same as output)
    # For zoom, we take a smaller crop and resize up
    crop_w = int(OW / zoom)
    crop_h = int(OH / zoom)
    # Pan: move crop center slightly
    cx = OW//2 + int(progress * 30)  # drift right 30px
    cy = OH//2 - int(progress * 20)  # drift up 20px
    x1 = max(0, cx - crop_w//2)
    y1 = max(0, cy - crop_h//2)
    x1 = min(x1, OW - crop_w)
    y1 = min(y1, OH - crop_h)
    
    # Extract and resize (camera move)
    crop = bg[y1:y1+crop_h, x1:x1+crop_w]
    frame_img = cv2.resize(crop, (OW, OH), interpolation=cv2.INTER_LINEAR)
    
    # Count vehicles per direction for brain
    counts = {'ew': 0, 'ns': 0}
    vehicles_this_frame = []
    
    for v in VEHICLES:
        x, y, angle, w, h = get_vehicle_pos(v, frame)
        # Only draw if on screen
        if -50 < x < OW+50 and -50 < y < OH+50:
            # Adjust for camera crop
            # (simplified: vehicles move in output coords, background drifts)
            # For simplicity, draw vehicles in output coords
            frame_img = draw_vehicle(frame_img, v[0], v[1], x, y, w, h, angle)
            vehicles_this_frame.append((x, y, w, h, angle))
            # Count by lane
            lane = v[4]
            if lane in ['ew_n', 'ew_s']:
                counts['ew'] += 1
            else:
                counts['ns'] += 1
    
    # Brain decision
    brain = brain_decision(frame, counts)
    if brain_history:
        _, last_brain = brain_history[-1]
    else:
        last_brain = {'q_hold': 0, 'q_switch': 0, 'decision': 'HOLD', 'phase': 0}
    
    # AI overlays - elegant thin outlines (not boxes)
    for (x, y, w, h, angle) in vehicles_this_frame:
        # Glowing outline (thin ellipse)
        overlay = frame_img.copy()
        cv2.ellipse(overlay, (int(x), int(y)), (w//2 + 3, h//2 + 3), angle, 0, 360, (0, 230, 118), 1)
        # Soft glow
        frame_img = cv2.addWeighted(overlay, 0.7, frame_img, 0.3, 0)
        # Small dot at center
        cv2.circle(frame_img, (int(x), int(y)), 2, (0, 230, 118), -1)
    
    # Top bar - minimal, cinematic
    # Semi-transparent gradient at top
    top_h = 70
    grad = np.zeros((top_h, OW, 3), dtype=np.uint8)
    for i in range(top_h):
        alpha = 0.7 * (1 - i/top_h)
        grad[i, :] = (int(5*alpha), int(8*alpha), int(12*alpha))
    frame_img[0:top_h] = cv2.addWeighted(frame_img[0:top_h], 0.4, grad, 0.6, 0)
    
    # SABZ logo text
    cv2.putText(frame_img, "SABZ", (28, 42), font_big, 1.0, (0, 230, 118), 2)
    cv2.putText(frame_img, "ADAPTIVE TRAFFIC AI", (28, 62), font, 0.45, (180, 190, 200), 1)
    
    # Vehicle count
    total_v = len(vehicles_this_frame)
    cv2.putText(frame_img, f"{total_v} VEHICLES", (OW-180, 42), font, 0.7, (255, 255, 255), 2)
    cv2.putText(frame_img, "LIVE", (OW-80, 62), font, 0.45, (0, 230, 118), 1)
    cv2.circle(frame_img, (OW-95, 58), 5, (0, 230, 118), -1)
    
    # Brain indicator - bottom right, minimal
    bx, by = OW-280, OH-120
    # Background pill
    cv2.rectangle(frame_img, (bx-10, by-30), (OW-20, by+50), (8, 10, 14), -1)
    cv2.rectangle(frame_img, (bx-10, by-30), (OW-20, by+50), (0, 230, 118), 1)
    
    cv2.putText(frame_img, "SABZ BRAIN", (bx, by-10), font, 0.45, (0, 230, 118), 1)
    # Q-values as thin bars
    qh, qs = last_brain['q_hold'], last_brain['q_switch']
    # Hold bar
    hw = int(min(abs(qh)/3.0, 1.0) * 120)
    cv2.rectangle(frame_img, (bx, by+5), (bx+120, by+12), (40, 45, 55), -1)
    cv2.rectangle(frame_img, (bx, by+5), (bx+hw, by+12), (0, 230, 118), -1)
    cv2.putText(frame_img, f"HOLD {qh:.2f}", (bx, by+28), font, 0.4, (160, 170, 180), 1)
    # Switch bar
    sw = int(min(abs(qs)/3.0, 1.0) * 120)
    cv2.rectangle(frame_img, (bx+130, by+5), (bx+250, by+12), (40, 45, 55), -1)
    cv2.rectangle(frame_img, (bx+130, by+5), (bx+130+sw, by+12), (255, 100, 100), -1)
    cv2.putText(frame_img, f"SWITCH {qs:.2f}", (bx+130, by+28), font, 0.4, (160, 170, 180), 1)
    
    # Decision (large, elegant)
    dec = last_brain['decision']
    dec_color = (0, 230, 118) if dec == 'HOLD' else (255, 176, 32)
    cv2.putText(frame_img, dec, (bx, by+48), font_big, 0.7, dec_color, 2)
    
    # Phase indicator - bottom left
    phase_name = "EW GREEN" if last_brain['phase'] == 0 else "NS GREEN"
    cv2.putText(frame_img, phase_name, (28, OH-28), font_big, 0.8, (0, 230, 118), 2)
    
    # Film grain (subtle)
    noise = np.random.normal(0, 4, frame_img.shape).astype(np.int16)
    frame_img = np.clip(frame_img.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    
    # Vignette
    yy, xx = np.mgrid[0:OH, 0:OW]
    cx_v, cy_v = OW//2, OH//2
    dist = np.sqrt((xx-cx_v)**2 + (yy-cy_v)**2)
    max_dist = np.sqrt(cx_v**2 + cy_v**2)
    vig = 1 - 0.25 * (dist / max_dist) ** 2
    frame_img = (frame_img.astype(np.float32) * vig[..., None]).astype(np.uint8)
    
    # Warm color grade (subtle)
    frame_img = frame_img.astype(np.float32)
    frame_img[:, :, 2] *= 1.04  # boost red slightly
    frame_img[:, :, 0] *= 0.97  # reduce blue slightly
    frame_img = np.clip(frame_img, 0, 255).astype(np.uint8)
    
    out.write(frame_img)
    
    if frame % 60 == 0:
        print(f"  Frame {frame}/{N_FRAMES} ({frame//30}s)")

out.release()
print(f"Done: {out_path}")
print(f"Brain switches: {switches}")
