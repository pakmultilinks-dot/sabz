# SABZ: AI-Adaptive Traffic Signals for Pakistan

**Category:** AI in Urban Tech
**Team:** Abdur Rehman, M. Bilal, Daud, Awais (Lahore Garrison University)
**Contact:** Abdur Rehman
**Repository:** https://github.com/pakmultilinks-dot/sabz
**Demo video:** `sabz_demo.mp4` (20 s side-by-side simulation)

---

## 1. The problem

Pakistan's traffic signals run on blind fixed timers. At a four-way junction,
one road with only two cars gets 25 seconds of green (about 22 of them wasted),
while the crossing road holds 50 cars on a 60-second red. Multiply this by
every signal in Lahore and the result is hours of lost time, fuel burned while
idling, and choking emissions, every single day.

Lahore's own history proves the pain is real: more than 130 traffic signals
were removed over two decades for "signal-free corridors," yet congestion
persisted because the underlying timing was never intelligent (Express
Tribune, May 2026). The Punjab government is now installing modern signals
with video vehicle detection at 20 major Lahore junctions (TEPA, Dec 2025),
which means the cameras are coming. What is missing is the AI brain that
decides, second by second, who deserves the green.

## 2. The solution

SABZ (سبز, "green") is an AI controller that replaces fixed signal timers with
real-time, camera-driven green allocation:

- **See:** existing CCTV / Safe City cameras watch each approach. A vehicle
  detection model (YOLO-class) counts cars per lane, every second.
- **Decide:** the adaptive controller extends green where queues are long,
  cuts it the instant a road clears (gap-out), skips empty approaches entirely,
  and never starves any road (max-out). Time-of-day plans handle patterns like
  the school rush: the school road automatically gets longer green in the
  morning, exactly as traffic demands.
- **Act:** commands go to the existing signal controller. No road digging, no
  inductive loops, no new hardware beyond a small edge computer per junction.

## 3. How it works (technical)

**Perception layer.** Camera frames are processed on-device (edge AI) to
detect and count vehicles per approach lane. Detection runs at 1 Hz for
control; the simulation models camera noise explicitly so results stay honest.

**Control layer (built and tested).** Actuated signal logic with:
- minimum green 8 s (safety), maximum green 45 s (fairness),
- gap-out: switch 3 s after the last vehicle clears,
- phase skipping for zero-demand approaches,
- priority plans for scheduled patterns (school hours, Friday prayer rush,
  stadium events).

**Simulation layer (built and tested).** A discrete-event 4-way intersection
simulator compares fixed-time plans against SABZ on identical traffic, over
three scenarios: asymmetric demand (the 2-vs-50 example), a school-morning
surge, and balanced rush hour. Five randomized runs per scenario.

## 4. Results so far

One-hour simulations, same traffic for both controllers, averaged over 5 runs:

| Scenario | Fixed-time avg delay | SABZ avg delay | Delay cut | Wasted green cut |
|---|---|---|---|---|
| Asymmetric (2 vs 50 cars) | 217 s/vehicle | 6 s/vehicle | 97% | 25% |
| School morning rush | 55 s/vehicle | 15 s/vehicle | 73% | 19% |
| Balanced rush hour | 102 s/vehicle | 34 s/vehicle | 67% | 2% |

Fuel wasted idling at a single asymmetric junction drops from about 73 litres
to about 2.4 litres per hour in simulation, with proportional CO2 reduction.
Assumptions: 0.6 L/h idling fuel per vehicle, 2.31 kg CO2 per litre of petrol,
single-lane approaches, 2 s saturation headway.

These are simulation results, not road measurements. They establish that the
control logic is sound; the next step is a camera-in-the-loop pilot.

## 5. Why this wins, and why now

- **Pakistan-first positioning.** Adaptive control exists abroad (SCATS since
  1975, SCOOT, InSync at 2,000+ US intersections, Delhi's ITMS rolling out
  now), but no AI adaptive signal layer is deployed in Pakistan. Lahore is
  installing the cameras right now, which makes this the exact moment for the
  software layer.
- **Retrofit, not rebuild.** Inductive loops require digging up roads.
  Camera-based control bolts onto cameras the city already owns, including
  Punjab Safe City Authority feeds.
- **Measured, not promised.** We ship a working simulator and a demo video,
  not slides. Judges can re-run every number.
- **Real-world precedent for impact.** CMU's Surtrec adaptive system cut
  travel time 25% and emissions 20% in Pittsburgh; Toronto is piloting InSync
  and SCATS against its 20-year-old fixed systems.

## 6. Roadmap

- **Idea (now):** proposal, simulator, demo video, public repo.
- **MVP (by finale):** camera-in-the-loop demo: YOLO vehicle counting on real
  intersection footage driving the SABZ controller live; dashboard showing
  per-approach queues and signal decisions.
- **Pilot (post-finale):** one junction with TEPA / City Traffic Police,
  before/after measurement of delay and queue length, the same metric our
  simulator already tracks.

## 7. Risks and mitigations

- **Camera occlusion at night / in rain:** infrared-capable cameras and
  conservative fallback to time-of-day plans when detection confidence drops.
- **Mixed traffic (bikes, rickshaws, lane indiscipline):** detection classes
  tuned for local vehicle types; queue estimation uses occupancy, not just
  counts.
- **Institutional adoption:** TEPA's current 20-junction upgrade is the entry
  point; the pilot is designed to plug into that program.

## 8. References

- Delhi Integrated Traffic Management System, adaptive signals rollout, Oct 2026
- TEPA: video vehicle detection at 20 Lahore junctions, ProPakistani, Dec 2025
- "Poor planning worsens traffic flow," Express Tribune, May 2026
- SCATS adaptive system (Sydney, 1975); SCOOT; Rhythm Engineering InSync
  (camera-based, 2,000+ US intersections)
- Surtrec (CMU): 25% travel-time and 20% emission reduction, Pittsburgh
- Toronto smart-signal pilot (InSync vs SCATS), RCR Wireless
- Lahore "AI traffic learning" plan with Safe City cameras, Dawn
