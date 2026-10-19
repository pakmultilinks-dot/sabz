# SABZ Blender Real - Cinematic 3D Demo

A cinematic 3D visualization of the SABZ AI traffic controller managing a Lahore-style intersection.

## What it is

- **Background:** Blender Cycles-rendered 3D intersection (golden hour lighting, buildings, roads, lane markings)
- **Vehicles:** Animated cars, auto-rickshaws, and motorcycles moving through the intersection
- **AI overlays:** Elegant detection outlines on every vehicle, live vehicle count
- **Brain:** The REAL trained DQN (`sabz_dqn_best.npz`) makes HOLD/SWITCH decisions every second, changing signal phases
- **Grade:** Warm cinematic color, film grain, vignette, subtle camera drift (Ken Burns)

## Files

- `scene.blend` - The full Blender 3D scene (intersection, buildings, vehicles, lighting)
- `build_scene.py` - Python script that builds the scene
- `composite.py` - Python script that composites animation + AI overlays
- `hero_bg_0001.png` - The Cycles-rendered background frame
- `sabz_real_blender.mp4` - Final 20-second video (1280x720, 30fps)

## How it was made

1. Built the 3D scene in Blender with Python (roads, buildings, vehicles, golden-hour sun)
2. Rendered hero background frame with Cycles (CPU, 48 samples + denoise)
3. Animated vehicles in 2D composited over the 3D background (OpenCV)
4. Ran the real DQN brain on vehicle counts to get HOLD/SWITCH decisions
5. Added cinematic post: grain, vignette, warm grade, camera drift

## Honest notes

- The 3D scene is **stylized**, not photorealistic (hardware limits prevent full photorealistic animation)
- Vehicles are 2D-composited over a 3D background (not full 3D animation)
- Brain decisions are from the real trained network
- No Indian/American elements; generic shop signs (no text)

## Run

Just play `sabz_real_blender.mp4`. No server needed.
