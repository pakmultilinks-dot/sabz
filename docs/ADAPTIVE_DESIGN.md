# SABZ adaptive control: engineering basis and implemented scope

This implementation is an interpretable scheduling algorithm, not a trained
neural policy or a replica of a commercial controller. It works through the
same safety kernel as the integration service. The hosted private demonstration
runs those Python sources in a browser worker; there is no independent
JavaScript implementation of signal policy. Recorded examples remain available
if the local browser Python engine cannot start.

## What deployed systems teach us

SCATS uses detector feedback to adjust cycle length, phase splits and offsets.
Offsets coordinate progression between junctions; a single-junction prototype
cannot claim this network function. Pedestrian requests are distinct inputs.
See [Transport for NSW's SCATS Core brochure](https://www.transport.nsw.gov.au/system/files/media/documents/2022/SCATS-Core-brochure-Final-web-spreads_0.pdf).

SCOOT models demand from detection and adjusts signal allocation and network
coordination. Seattle documents an operational 32-intersection deployment that
detects traffic, predicts flows and adjusts time available to movements:
[City of Seattle](https://seattle.gov/transportation/projects-and-programs/programs/technology-program/mercer-scoot).
The [original TRL SCOOT report](https://www.trl.co.uk/uploads/trl/documents/LR1014.pdf)
and [FHWA detector handbook (archived)](https://www.fhwa.dot.gov/publications/research/operations/its/06108/03.cfm)
give engineering background. Their benefits are not SABZ performance claims.

Local pressure-based policies provide a research basis for using adjacent queue
measurements without requiring neural training. Finite receiving-road storage
matters: [Gregoire et al., capacity-aware back-pressure](https://arxiv.org/abs/1309.6484)
explains problems with infinite-storage assumptions. SABZ's formula below is
pressure-inspired; it is not the paper's exact normalized-pressure algorithm
and inherits none of its mathematical stability claims.

## Implemented policy

For each measured through movement, let `q` be the upstream queue, `d` the
receiving-road count, `K` its capacity, `a` vehicles approaching within four
seconds, and `lambda` the recent measured arrival rate. The demand score is:

```text
supply = max(0, 1 - d / K)
movement_score = (max(0, q - d) + 0.5 * (a + 4 * lambda)) * supply
phase_score = sum(movement_score for compatible through movements)
```

Full receiving roads contribute no usable demand. If both phase groups lack
receiving space, the kernel holds all-red. If only one group is available, the
next phase selection can skip the unavailable or empty group after full
clearance. The cabinet model permits this selection only in all-red, never by
changing a green directly to its conflict.

Once minimum green is complete, the policy checks: blocked current supply;
eligible opposing demand waiting at least 60 seconds; a three-second actual
passage gap; then a pressure advantage greater than three score units.
Recent arrival-rate predictions do not continually reset the actual passage-gap
timer. A full receiving road has no unconditional service guarantee.

Pressure switching also waits for a bounded batching target so frequent changes
do not consume excessive clearance time. The target uses a Webster-inspired
cycle estimate from measured critical flow ratios: saturation is assumed to be
0.5 vehicle/second per approach in this bench, cycle lost time is approximated
as 10 seconds, and the target cycle is bounded to 40–100 seconds. Phase targets
are proportional to critical demand and bounded to 8–45 seconds. Gap, blockage
and waiting-time rules can end a batch sooner, subject to the safety kernel.
This is an approximate bench heuristic, not an engineered timing plan for a
particular road. The [FHWA timing toolbox](https://ops.fhwa.dot.gov/publications/signal_timing/03.htm)
documents Webster's original isolated-junction estimate and its assumptions.

The kernel owns minimum/maximum green, yellow, clearance, sensor freshness and
fault handling. The separate cabinet process owns its own timings, legal lamp
groups and lease expiry. Neither the optimizer nor the browser can directly
energize a physical lamp; no physical output adapter is implemented here.

## Inputs and integration

Observation v1 remains supported as legacy queue-actuated behavior. It does not
invent downstream measurements. Observation v2 adds five required four-approach
maps: `downstream_counts`, `downstream_capacity`, `approaching`, `arrival_rate`
and `oldest_wait_s`. All values are validated before acceptance. The camera SDK
accepts these maps as `traffic_state`. The audit journal records the entire
validated observation, including its schema version and traffic fields.

Example, using measured values from a calibrated producer:

```python
client.send(
    {"N": 12, "S": 8, "E": 2, "W": 1},
    healthy=True, conflict_clear=False,
    traffic_state={
        "downstream_counts": dict.fromkeys("NSEW", 3),
        "downstream_capacity": dict.fromkeys("NSEW", 20),
        "approaching": dict.fromkeys("NSEW", 1),
        "arrival_rate": dict.fromkeys("NSEW", 0.1),
        "oldest_wait_s": dict.fromkeys("NSEW", 5),
    },
)
```

These values are illustrative. The existing experimental YOLO producer does not
measure these fields and continues to send v1 with clearance false. Camera
calibration, label-based accuracy checks and actual receiving-road sensors are
still required before treating a feed as v2 traffic observations.

## Demonstration and evaluation

`python -m examples.build_showcase` generates examples and a benchmark. Every
controller in each paired comparison uses exactly the same pre-generated
Poisson arrival stream, identified by SHA-256. Upstream travel takes eight
seconds; vehicles join finite-service point queues. Discharge is one vehicle
per two seconds per approach after a one-second start-up loss. Receiving space
is finite. The spillback scenario imposes external receiving-road occupancy.
Observations are ideal; this is not camera validation or vehicle-trajectory
simulation. No collision, braking, turning or pedestrian model is included.

The fixed baseline uses 25-second greens, not a claimed optimally tuned plan.
The actuated baseline uses the documented queue/gap rules. The adaptive mode
uses the new policy. All share the same safety kernel and cabinet model.

The report covers seven scenarios and seeds 41, 83, 119, 211 and 307 for 600
seconds each (105 controller runs). It reports accrued queue delay per arrival,
served and unfinished vehicles, completed-wait p95, maximum observed wait and
phase changes. Accrued delay includes terminal queued vehicles; completed-wait
p95 has completion censoring, so it must be read alongside unfinished counts.
The displayed seed variability is descriptive, not a confidence interval or a
significance test. Policy design was iterated using synthetic examples and these
benchmarks; the scenarios are not a blind held-out field evaluation.

All scenario averages, including regressions, appear in the demonstration. The
[FHWA validation guidance](https://ops.fhwa.dot.gov/publications/fhwahop13031/index.htm)
supports explicit operating objectives and careful baseline evaluation. No
simulation percentage here is claimed as a Pakistan road improvement.

## Show it to a visitor

1. Open the private hosted Signal Lab and play the default paired example.
2. Scrub time and inspect actual lamp states, queues, decision scores and reasons.
3. Choose a new seed and demand multiplier; run a fresh Python simulation.
4. Switch to downstream blockage or camera loss and inspect the response.
5. Open the complete benchmark and download the CSV and exact Python source.

The browser uses a self-hosted Pyodide 314.0.7 runtime. Its upstream URL and file
hashes are retained under `showcase/dist/runtime/PROVENANCE.json`; the upstream
license is included. The browser downloads no camera frames or API credentials,
and the hosted demo has no route to a physical controller.

## Bounded approach protection and fairness (2026-10-27)

Observation schema 3 extends schema 2 with three exact N/S/E/W maps:
`nearest_moving_distance_m` (0..500 or null), `max_approach_speed_mps`
(0..70), and `distance_uncertainty_m` (0..20). Null distance and zero speed
must occur together. These are aggregate detections, not vehicle identities.
The publisher must report only vehicles moving toward the stop line on the
relevant approach, and must establish metric calibration independently.
No pixel-to-metre conversion or calibrated camera is supplied by this change.

The kernel uses the nearest distance minus uncertainty and maximum approach
speed times observation age. A moving approach within 70 m and a conservative
arrival estimate of at most 6 s can delay an early adaptive phase termination.
Speed must exceed 0.5 m/s. A car travelling 10 km/h at 70 m does not hold the
phase. These are bench assumptions, not approved universal road parameters.
Using aggregate minimum distance and maximum speed is conservative and may
combine different vehicles. Detection errors and occlusion remain unresolved.

Maximum green and fixed-plan termination override this extension. Faults and
sensor unavailability still initiate yellow and clearance. A stream of new
vehicles cannot prolong green beyond the local maximum. No abrupt green-to-red
change is permitted by this feature.

Protection requires metric observations no older than 200 ms. Status explicitly
reports `unavailable`, `expired`, `clear`, or `bounded_hold`. Legacy v1/v2 and
expired v3 still operate the existing UNPROTECTED bench scheduler; this is NOT
an approved road fallback. A deployment that requires approach protection must
not connect this bench controller to road outputs. A calibrated independent
sensor, cabinet integration, a site-approved fallback plan, and its interlock
are prerequisites. The process-level cabinet emulator does not independently
verify vehicle distance, and a compromised sensor/host can forge measurements.

After service, actual eligible demand on the opposing phase gets the next turn,
even if the previous phase retains a much larger queue. An empty or blocked
receiving phase can be skipped. Startup still selects by demand. Maximum green
bounds monopolization; this is not a guarantee under sensor failure, blocked
receiving roads or turns. Emergency preemption (v5) is implemented as an
explicit reader-authenticated request: it may end green early but never skips
yellow or all-red, expires after 60 seconds, and cannot override a latched
fault. Pedestrian queue demand (v4) raises demand on its approach but cannot
hold a phase or create a crossing interval.

Precise metric distance/speed fields are omitted from SQLite observation audit
records. Counts, timestamps and decisions remain local and need a deployment
retention policy. No frames, faces or plates are accepted by this protocol.
This is data minimization, not a claim of legal compliance or anonymity.

`examples/render_engineering_video.py` renders the actual Python kernel outputs
for fast/slow approaches, maximum termination and 70 vehicles versus one bike.
`validation/approach-video-traces.json` contains the reproducible underlying
states. The video uses repeated synthetic detections, not realistic vehicle
trajectories, hardware measurements, collision analysis or field evidence.

Next acceptance gates: calibrated authorized local sensing or non-imaging
radar; mixed Pakistani traffic including motorcycles and occlusion; measured
capture-to-cabinet p50/p95/p99/max latency under contention; independent physical
conflict monitor/watchdog; signed configuration/updates and per-device identity;
hardware-in-loop tests; permissioned shadow trial and traffic-engineer review.
National operation should keep timing at each junction during WAN failure and
send minimized aggregate telemetry to corridor services. That architecture is
not implemented or validated by this bench change.

## Integrated algorithm revision (27 October 2026)

The active policy now requires receiving space for one vehicle on both members
of a shared phase. Green targets combine the previous bounded rate allocation
with a queue-service estimate (2 s startup plus the largest approach queue /
0.5 vehicles per second), clipped to 8..45 s. When actual opposing demand exists,
expiry of that target can yield even if current pressure is greater. The kernel
still owns minimum/maximum timing, bounded approach extension and clearance.
This changes the bench policy; old benchmark files are not evidence for the
new revision unless regenerated. The 105-run virtual qualification has been
regenerated. No field benefit is inferred from those runs.

`perception.py` and `sensor_ingest.py` now provide calibrated coordinate math,
local tracked-motion aggregation and an authenticated metadata bridge. They do
not supply trained image-detection weights or prove actual calibration accuracy.
See [ALGORITHM_INTEGRATION.md](ALGORITHM_INTEGRATION.md) for the contracts and
remaining limits. The compiled-C++ integration fixture exercises these aggregates
through the real runtime and serial adapter into the shared firmware core.

The sender SDK now uses SQLite WAL with FULL synchronous durability and a 100 ms
lock timeout. Submission timing is instrumented separately from post-acceptance
status polling. One service run observed a 1.17 s first-sample outlier; a later
instrumented run did not reproduce it. No hard latency guarantee or causal fix
for that outlier is established.
