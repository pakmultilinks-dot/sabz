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

**Safety layer (hard guarantee, not learned).** The founder's non-negotiable
rule: the signal must never cut green while a car is close to the stop line,
even if the visible queue is empty. Every vehicle is tracked with distance and
speed; a 70 m dilemma zone on each green approach is checked every second. If
any vehicle is inside it, a switch decision is overridden and green extends
(up to a 60 s fairness cap). Tested: without this rule, the controller tried
51 unsafe cutoffs in a platoon scenario; with it, all 240 attempts were held
and zero unsafe cutoffs executed. Safety is physics, not AI.

**Perception layer.** Camera frames are processed on-device (edge AI) to
detect and count vehicles per approach lane, 120 m range. Detection runs at
1 Hz for control; the simulation models camera noise explicitly so results
stay honest.

**Control layer (built, tested, training).**
- Actuated baseline: min green 8 s, max green 60 s, gap-out, phase skipping,
  never starves any road.
- Learned controller: our own Deep Q-Network trained from scratch inside the
  simulator (10-state, 2-action, 1200 episodes across demand scenarios). The
  network learns efficiency; safety stays a hard environment rule it cannot
  override.

**Location intelligence (built).** The system reads OpenStreetMap around each
intersection, finds schools, offices, mosques, markets and hospitals, maps
each to its approach by bearing, and auto-generates time-of-day priority
plans: school runs 07:15-08:30 and 13:30-15:00 on schooldays, office commutes,
Jummah 12:00-14:30 on Fridays near mosques, evening bazaar hours. No
hand-tuning per junction; the map teaches the schedule.

**Simulation layer (built and tested).** A kinematic 4-way intersection
simulator (vehicle agents with distance/speed, queue dynamics, free-flow
passes) compares fixed-time plans against SABZ on identical traffic: asymmetric
demand, school-morning surge, balanced rush hour.

## 4. Results so far

Kinematic simulations (delay measured against free-flow travel time, same
traffic for both controllers, averaged over 3 one-hour runs; safety layer
active on both):

| Scenario | Fixed-time avg delay | SABZ actuated avg delay | Delay cut |
|---|---|---|---|
| Asymmetric (2 vs 50 cars) | 8.7 s/vehicle | 5.0 s/vehicle | 43% |
| School morning rush | 11.0 s/vehicle | 8.8 s/vehicle | 20% |
| Balanced rush hour | 179.7 s/vehicle | 11.9 s/vehicle | 93% |

Safety: 51 unsafe green-cutoffs attempted without dilemma-zone protection in
the danger test; 240 attempted with protection, all held, zero executed.
The learned DQN controller is training now; it is evaluated against the
actuated baseline on the same scenarios before the finale.

These are simulation results, not road measurements. They establish that the
control logic and the safety guarantee are sound; the next step is a
camera-in-the-loop pilot.

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

- **Idea (now):** proposal, kinematic simulator with proven safety guarantee,
  location-intelligence module, demo video, public repo.
- **MVP (by finale):** trained DQN controller evaluated against the actuated
  baseline; POI-derived time plans for a real Lahore junction; camera-in-the-
  loop demo with vehicle counting on real intersection footage driving the
  SABZ controller live; dashboard showing per-approach queues, dilemma-zone
  holds, and signal decisions.
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
