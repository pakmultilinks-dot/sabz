# Working algorithm path and remaining limits

The active path is:

local detector tracks -> surveyed road-plane projection -> speed/queue/arrival
aggregation -> authenticated schema-3 input -> capacity-aware allocation and
fair turns -> bounded approach extension -> timed signal kernel -> independent
emulator OR explicitly selected low-voltage serial bench -> separate readback.

The new `sabz_edge.perception` module takes temporary detector tracks. It does not
include a trained image detector, create tracks from images, survey a camera or
prove that a calibration is accurate. The historical YOLO quadrant counter is
not a substitute for these measurements. No locally validated detector weights
are included in this path.

## Algorithms implemented and connected

| Algorithm | Implementation and check |
|---|---|
| Pixel-to-road geometry | Four surveyed correspondence pairs fit a planar homography per approach; singular geometry, invalid coordinates and points outside the surveyed road region are rejected |
| Vehicle motion | Longitudinal distance change over source-frame time; invalid speeds and large lateral jumps withdraw health |
| Queue/wait estimate | Near-stationary tracked vehicles counted per approach; stop duration tracked locally; motorcycles count as demand |
| Arrival measurement | Each track's crossing of an upstream line at 80% of surveyed length counts once; standing queue growth/track creation are not treated as arrivals |
| Forecast input | Measured trailing 30-second arrival rate contributes to a bounded four-second demand horizon; no trained predictive model claim |
| Receiving supply | A shared phase requires space for one additional vehicle on BOTH receiving approaches; a free empty lane cannot hide a blocked paired lane |
| Green allocation | Queue service estimate and rate-based cycle allocation form an 8..45 s target; estimates use uncalibrated bench saturation/startup assumptions |
| Fair turn | Eligible actual cross-demand gets the next turn; an expired allocated budget can yield despite a larger current queue |
| Approach protection | Fresh metric estimates can hold an early termination inside 70 m / six-second arrival window; maximum/fixed timing and faults still limit it |
| Signal timing | Minimum/maximum green, full yellow and clearance; positive clearance required; no conflicting active groups |
| Failure handling | Stale/unhealthy sensing, local latched faults, independent command lease; board also has a wired stop loop |
| Transport security | TLS, separated credentials, durable replay rejection, bounded framing; serial CRC is corruption detection, NOT authentication |

The time, rate, distance and saturation constants are bench parameters, not
approved road settings. The eight-second allocation minimum does not override
the kernel's configured minimum. For a shared phase the conservative receiving
check may sacrifice usable capacity until lane-level movements are supported.

## Run the detector metadata bridge

1. Obtain surveyed pixel/road point pairs for EACH approach, metric width/length
   and an externally measured uncertainty bound. Ground coordinates are lateral
   position and distance upstream of the stop line; the stop line is distance 0.
2. Supply an authorized local detector/tracker producing bottom-centre road
   contact points, temporary IDs and approach assignments. Validate tracking,
   motorcycle accuracy, lighting and occlusion independently.
3. Supply separate real conflict clearance, receiving-road counts/capacities and
   sensor-health inputs. This bridge never infers clearance from an empty image.
4. Connect JSON lines from that process to the bridge. Every line contains:
   `frame_time_s`, `captured_at`, `detections`, `conflict_clear`,
   `downstream_counts`, `downstream_capacity`, `sensors_healthy`.
   Each detection contains exactly `track_id`, `approach`, `pixel_x`, `pixel_y`,
   `vehicle_class` (car/motorcycle/bicycle/bus/truck).
5. First validate aggregate output without connecting to control:

```powershell
Get-Content local-detections.jsonl | python -m sabz_edge.sensor_ingest --calibration surveyed-calibration.json --validate-only
```

`examples/calibration.example.json` is a synthetic mathematical example ONLY.
It is not valid for any real camera and must not be copied into an installation.
Source-frame times must increase and reflect actual exposure timing for speed
estimation. `captured_at` is wall-clock Unix seconds from original acquisition,
not the time a buffered frame happens to be processed.

For live metadata piping, configure the sensor token and the real endpoint:

```powershell
python local_detector.py | python -m sabz_edge.sensor_ingest --calibration surveyed-calibration.json --endpoint https://edge.internal:8099 --ca-file private-ca.pem --state data/metric-sensor.sqlite3
```

`local_detector.py`, actual surveyed calibration and independent sensor inputs
are integration requirements, not files already supplied under those names.
Recorded old footage cannot be relabelled fresh real-time data for control.

The first frame is unhealthy while motion initializes. New tracks then use a
conservative 70 m/s upper bound until speed is established; that is not a measured
speed. This avoids assuming a new fast vehicle is stationary, but may hold green
unnecessarily until the next valid sample. Missing tracks, implausible motion or
a frame gap over 200 ms withdraw health. Temporary tracks expire after two
seconds and are capped; identity changes and occlusion can still corrupt counts.
Independent quality assessment is necessary: blank detections do not prove the
camera sees all traffic. Persons are tallied into pedestrian_queue demand and
never silently treated as vehicle movements; other unsupported road users fail
this through-only bridge.

Raw frames and temporary track IDs are not sent in the observation or audit.
The CLI prints only accepted sequence information, or aggregate values in
validate-only mode. Rejected detector input immediately publishes unhealthy
state (when connected) and exits without logging raw input. The kernel's existing
fault clearance is still a bench behaviour, not a site-approved road fallback.

## Models that are intentionally not given signal authority

`sabz_rl.py`, `sabz_intelligence.py`, `sabz_predict.py` and old NPZ checkpoints are
research paths. Their state schema, accuracy, held-out benefit, reproducibility
and failure behaviour have not been validated for this integration. In
particular, random exploration, online fine-tuning and shape-tolerant checkpoint
loading do not belong in the active safety-critical path without qualification.
All working control algorithms above use explicit deterministic contracts.

## Meaning of completion

Software tests now exercise measurement aggregation into the actual API and
scheduler, allocation/supply/fairness, approach protection, timed transitions,
malformed inputs and the compiled C++ bench controller. Virtual tests remain
point-queue experiments. The system is NOT yet complete for public roads:
image detector/tracker validation, real calibration, physical board build/flash,
electrical readback, general turns/pedestrians, approved fallback, production
security and integrated hardware/site acceptance remain open.

## Explicit queue and rush matrix (27 October 2026)

`python -m examples.run_user_scenarios` runs 36 named cases plus every combination
of the selected queue values {0,1,50,100} across four approaches (256 cases).
This is exhaustive over those four selected values, not all possible real
traffic situations. Results and transitions are saved under
`validation/user-scenario-matrix.json`, `validation/exhaustive-queue-grid.json`
and `validation/user-scenario-results.md`.

Checks include conservation, conflicting outputs, minimum/maximum green,
yellow and clearance durations, new greens into blocked receiving links,
occupied-intersection release, stale/unhealthy sensing deadlines, initial
service opportunities and bounded fast/slow approach extensions. The model
assumes .5 vehicle/s discharge per approach with simplified startup time;
receiving supply is externally prescribed in these cases. It does not model
vehicle collisions, turns, pedestrians, real tracking or driver behaviour.

The matrix exposed repeated short green intervals under sustained congestion:
old vehicles remaining in both queues repeatedly triggered waiting-time priority
even after their phase had just received green. The policy now records each
phase's most recent GREEN OPPORTUNITY and requires that to be overdue before
old individual waits trigger the same override again. This does not prove a
vehicle actually departed; the controller's requested opportunity is distinct
from physical readback and measured discharge.

For the same synthetic 100/100/100/100 initial queues over 300 s, served volume
changed from 200 to 276 after this correction; 124 vehicles still remained.
This is a regression observation in this model, not a claimed field benefit.
A regression test preserves batching and service under this equal-heavy case.
The previous report is retained as `user-scenario-before-fairness-fix.json`.

In the 50/1/1/1 case, NS green runs from 2 to 47 s; 27 N vehicles remain when
yellow begins. EW receives green at 52 s after 3 s yellow and 2 s clearance.
Thus the small cross-demand receives service before the large queue empties.
Equal demand does not imply simultaneous four-way green: the supported grouping
is NS versus EW. A fifth approach is explicitly rejected, not silently mapped.

Over-capacity scenarios intentionally leave residual/growing queues. Their PASS
means the named timing, service and conservation checks passed; it does not
mean congestion was eliminated. True queue sizes above 500 remain in the model;
the schema-3 observation is capped at 500 and saturation ticks are reported. Real sensor
overflow/health semantics still require integration validation.


Metric observation schema 3 now accepts up to 500 queued/approaching vehicles
per approach and receiving counts/capacities up to 500. Schemas 1/2 retain their
100-vehicle bounds. The calibrated producer accepts up to 2000 detections per
frame, bounds retained tracks to 4000 and withdraws health on overflow. A 250-car
queue is now tested through producer and schema without clipping. This is an
input-range extension, not a claim that an actual camera can accurately track
that density. Larger/occluded queues still need quality/fallback validation.
