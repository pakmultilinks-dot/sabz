# Street-level 3D demonstration

Run `python examples/render_street_3d.py` with NumPy and OpenCV installed.
Output: `validation/sabz-street-level-3d.mp4`, 1280x720 at 15 fps.
Three simultaneous perspective views share a single world state: driver,
roadside, and signal camera. All signal decisions come from `sabz_edge.core`.
The renderer uses local procedural meshes; it does not access cameras or upload
frames. This is a schematic 3D engineering scene, not photorealistic footage.

The 48-second first sequence includes a fast approach, a slow approach, and
70 queued vehicles versus one waiting bike. Queue counts feed the controller;
only a representative subset of the large queue is drawn. Motion uses a
simplified stopping-speed relation with 2.5 m/s^2 deceleration. Cars that have
passed the stop line continue through. Yellow response, driver variability,
collision resolution, pedestrians, turns, occlusion, rain/night, sensor faults,
and attack visualization are not validated by this first sequence.

Replay checks confirmed: fast approach holds until the vehicle passes at
12 s, slow approach begins yellow at 10 s, maximum begins yellow at 62 s,
full yellow ends at 65 s, and the waiting bike receives green at 67 s.
No conflicting NS/EW greens occur in any rendered trace. These checks concern
the synthetic traces only. They do not establish physical stopping safety.

The raw controller and motion states are in `validation/street-3d-traces.json`.
Each scenario resets independently. The fairness scene starts its visible
window at controller time 55 s after continuous warm-up ticks, not a skipped
clock interval. Remaining work is to replace simplified motion with a validated
microsimulation/driver model, enumerate scenario coverage, and connect approved
bench sensors and a physical cabinet interlock for hardware-in-loop tests.
