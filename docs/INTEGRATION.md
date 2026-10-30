# SABZ edge integration v0.1

Status: working bench integration release. The CLI routes outputs to an
independent-process cabinet emulator. The default path has no physical outputs. An explicit ESP32-S3 low-voltage
serial/GPIO bench implementation is now available; see
[PHYSICAL_BENCH.md](PHYSICAL_BENCH.md). No road-cabinet NEMA/NTCIP/PLC adapter is included.
This is not a certified road controller. The service is deployable on an edge
computer and reachable over authenticated HTTPS; a cloud connection is not
required for local control.

**Emergency preemption (schema v5).** A reader-token `POST /v1/preemption`
endpoint and an `emergency` field in the observation schema request a phase
for an emergency vehicle on one approach. This is an explicit authenticated
request, never automatic vehicle detection. The safety kernel still enforces
yellow and all-red clearance, a 60-second request expiry, and latched faults —
preemption can end green early but can never skip clearance or override a
fault. It is a bench feature, not a certified emergency-vehicle preemption
system.

## Supported topology

One intersection, one authenticated observation producer, two opposing
through-only phases (NS and EW). Turns, railway
interaction and coordinated junctions are outside this release. Pedestrian
queue demand (schema v4) is accepted as an input count and starts a protected
walk: the walk accompanies the parallel vehicle green as a GREEN sub-state,
holds it for at least `walk_min` (default 7s) against demand switches, and
persistent demand extends it up to `walk_max` (default 20s from green entry).
The controller reports reason `pedestrian_walk` and exposes `walk_active` in
snapshots; safety-class exits (emergency preemption, sensor loss, maximum
green, fixed plan) still end the walk, and yellow/all-red clearance is never
compressed.

Accessibility-aware timing (optional `accessibility` timing config) assigns
each approach a multiplier from 1.0 to 3.0 for sites with a hospital, school
or senior crossing. A phase uses the maximum multiplier of its two approaches
and scales `walk_min`, `walk_max`, `min_green`, `max_green` and the fixed-plan
green — so flagged crossings get proportionally longer walks and greens.
Yellow and all-red clearance are never scaled, safety exits still override,
and the active map is exposed as `accessibility` in snapshots. Emergency
preemption (schema v5) is an
explicit authenticated request for one approach's phase; it never skips
clearance and is not automatic detection. Do not use its two-phase
configuration for a real junction containing these movements. Counts are
nonnegative bounded numerical demand estimates.

**Stopped-vehicle class breakdown (schema v6).** The producer can report how
many stopped vehicles of each class (`car`, `motorcycle`, `bicycle`, `bus`,
`truck`) are queued on each approach. The field is optional at the producer —
when present it escalates the packet to schema v6 and must cover all four
approaches with the exact class vocabulary; `person` tallies as a pedestrian,
never as a vehicle. The dashboard exposes the latest breakdown and the report
summarizes it per class and per approach. It is an input metric only — the
scheduler does not yet weight phases by vehicle class.

Observation v1 uses the legacy queue-actuated scheduler. Observation v2 enables
the capacity-aware adaptive policy with downstream supply, approaching demand,
measured arrival rates and waiting time. The safety kernel and cabinet remain
outside that optimizer. See [ADAPTIVE_DESIGN.md](ADAPTIVE_DESIGN.md) for the
implemented formula, deployed-system research and demonstration methodology.

`producer -> authenticated observation API -> durable acceptance -> latest
observation -> 20 Hz target control loop -> timed state machine -> inherited local pipe
-> independent cabinet emulator -> acknowledged emulated readback`

Telemetry is a separate read-only role. There is no command, model upload,
runtime timing-edit, feedback-learning or fault-reset endpoint. There is no
online learning or random controller exploration. The deterministic actuated
baseline is intentional until a model passes independently held-out evaluation.

## Run from a checkout (Python 3.11+)

The edge service and SDK use the Python standard library. NumPy, YOLO and the
historical research dependencies are not needed for this service.

PowerShell, from the repository root:

```powershell
$env:SABZ_CAMERA_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:SABZ_READER_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:SABZ_TIMING_FILE = 'config/bench-timing.json'
python -m sabz_edge.server
```

Keep credentials in your process secret environment; do not commit them or put
them into URLs. Configure the same camera credential in the producer. In a
second terminal, with that credential already available:

```powershell
python -m examples.bench_sender --seconds 40
```

This sender explicitly fabricates a clear conflict zone for the **bench**.
Never treat it as a sensor. Observe the actual service state:

```powershell
Invoke-RestMethod http://127.0.0.1:8099/v1/status -Headers @{Authorization="Bearer $env:SABZ_READER_TOKEN"}
```

An installed entry point is also available after `python -m pip install .`:
`sabz-edge`. Do not run multiple service instances for the same intersection.
Each intersection requires its own credentials, persistent state and process.

## Network deployment

Set `SABZ_BIND` to a numeric interface address and provide `SABZ_TLS_CERT` and
`SABZ_TLS_KEY`. Binding beyond loopback without TLS fails at startup. Use a
certificate trusted by the camera's CA trust store, valid for the actual host.
The SDK verifies certificates, uses direct connections (ignoring ambient proxy
settings), and refuses redirects. For a private CA, pass
`ca_file="/path/to/ca.pem"` to `CameraClient` or configure the host trust store.
Do not disable verification.
No CORS access is provided; browser dashboards should use a controlled backend.

Restrict the network listener to a private OT network/VPN and allowlisted
producer/monitoring hosts. Terminate public access at a separately hardened
gateway if needed; this small edge server is not an internet ingress platform.
TLS minimum is 1.2; two-second inactivity timeouts, a three-second absolute
connection deadline (including handshake and headers), 16 workers, a 4 KiB
observation limit, 16 KiB aggregate header limit, a 2 KiB request-line limit and
a shared 20-request/second token bucket bound application resources. Unknown
routes share that request budget. Gateway and firewall limits are still required;
these application bounds do not establish resistance to network-level flooding.

Container recipe:

1. Place a trusted `server.crt` and matching `server.key` under `deploy/tls/`.
   This directory is gitignored. Make the key readable only by the service UID
   (10001) and administrators.
2. Supply distinct camera/reader tokens through your deployment secret manager.
3. Run `docker compose up --build -d`. The host port defaults to loopback;
   set `SABZ_HOST_IP` to a private interface address for other devices.
4. Mount persistent storage and back up `edge.sqlite3` using SQLite's backup
   facilities. Do not delete the replay database to work around a rejected packet.

The image runs as UID 10001 with a read-only root filesystem and dropped Linux
capabilities under Compose. The Docker health check only checks listener
availability; use `/healthz` and authenticated `/readyz` for application health.
Pin the tested image/base digest and scan it before an actual release. Image
signing, certificate rotation and host hardening are deployment responsibilities.

## API contract

`POST /v1/observations` requires the camera bearer token and JSON:

```json
{
  "schema_version": 1,
  "sequence": 123456,
  "captured_at": 1790000000.0,
  "counts": {"N": 12, "S": 8, "E": 2, "W": 1},
  "conflict_clear": false,
  "healthy": true
}
```

The timestamp above is illustrative; send current Unix UTC seconds, captured
when sensing occurred. Packets older than 3 seconds or over 1 second into the
future are rejected. Sender and edge wall clocks must be synchronized. Once
accepted, freshness uses monotonic time and preserves the packet's existing age.

Exactly the documented fields are accepted. Counts must contain exactly the
four approaches, each finite and between 0 and 100 in schemas 1/2; schema 3 allows up to 500
queued/approaching vehicles and receiving counts/capacities. Booleans are not counts.
Schema versions are cumulative: v2 adds the downstream/approaching dictionaries,
v3 the approach distance/speed fields, v4 `pedestrian_queue`, v5 `emergency`,
and v6 `class_counts` — a per-approach stopped-vehicle breakdown keyed
N/S/E/W, each a dict of exactly `car`, `motorcycle`, `bicycle`, `bus`, `truck`
with whole counts 0–500. A v6 packet must carry every earlier field as well;
older packets remain accepted unchanged.
`healthy` and `conflict_clear` must be literal JSON booleans. Sequence is a
strictly increasing nonnegative signed 64-bit integer, scoped to the configured
`SABZ_SOURCE_ID`. Acceptance and audit insertion share a durable transaction.
The sender must persist its sequence across restarts; the supplied SDK does so.
Use only one producer per configured identity. Token rotation retains the source
identity and its watermark. Capture time cannot regress, even when sequence
increases; capture watermarks also persist across restart. Old databases gain
this column at startup (their initial capture watermark is unknown until the
first new observation). A compromised producer can jump the watermark and
cause denial of service; recover only through an audited maintenance procedure.

`202` means accepted, **not** a signal actuation acknowledgement. Invalid JSON,
duplicate keys and schema violations return `400`; bad credentials `401`;
replays `409`; oversized bodies `413`; wrong content type `415`; rate limiting
`429`; storage faults `503`. Missing/conflicting length headers are rejected;
chunked uploads are unsupported. Unknown routes return `404`.

`GET /v1/status` requires the reader token. It returns controller stage,
candidate phase, logical lamps, last requested output, separately acknowledged
`cabinet_readback`, sensor age and fault state. A requested green can remain
all-red in the cabinet until its own clearance completes; the two are deliberately
distinguished. Readback is still an emulator, not measured physical lamps.
During `ALL_RED`, `phase` names the next candidate; lamps are authoritative.
`field_ready` is always false. `ready` only means the bench loop and sensor are
healthy; it does not establish clearance or field approval.

`GET /readyz` uses the reader token and returns 503 when the bench is not ready.
`GET /healthz` returns minimal unauthenticated loop liveness, including a recent
completed tick. No token, raw frame or credential is returned in status/logs.
There is no legacy `/camera` or `/feedback` route.

`POST /v1/preemption` requires the **reader** token (not the camera token) and
a JSON body `{"approach": "N" | "S" | "E" | "W"}`. It returns `202` when the
request is recorded, `400` for a malformed body or unknown approach, and `401`
without the reader token. The request asks the controller for that approach's
phase; it is honoured only while the request is fresh (60-second expiry) and
subject to the safety kernel: yellow and all-red clearance are always run,
and a latched fault still wins. The same request can be carried in an
observation's `emergency` field (schema v5: exactly one of N/S/E/W set to 1).
There is no automatic emergency-vehicle detection — COCO classes do not
include ambulances, and detection-based preemption would be unsafe to guess.
Status exposes the active request under `controller.preemption`.

`GET /v1/metrics` requires the reader token and returns the local dashboard
view: `mode`, `field_ready`, `now`, `sensor_age_s`, `sensor_fresh`,
`loop_healthy`, `last_error`, the full `controller` snapshot, `metrics` (the
latest accepted feed: sequence, schema version, capture age, health flags and
per-approach `counts`, `approaching`, `arrival_rate`, `oldest_wait_s`,
`pedestrian_queue`, `emergency` dictionaries keyed N/S/E/W, plus
`class_counts` (schema v6: per-approach stopped-vehicle counts by class),
`recent_transitions` — the last 20 `transition_intent` audit events with parsed
payloads — and `recent_alerts` — the last 20 edge-triggered `alert` events
(fault latch, preemption request, sensor loss/recovery, audit failure), each
deduplicated so an alert fires once per state change rather than every tick.
`metrics` is `null` until the first feed arrives. If the control lock
is busy the endpoint answers `400` with `{"error": "control_lock_busy"}` rather
than delaying the control loop; retry on the next refresh. The snapshot is
aggregates only — no frames, tokens or raw detections leave the edge.

Fault and preemption alert events are surfaced on the dashboard and via a
local alert log. The runtime journals an `alert` event on each state edge:
a fault latching, a preemption request arriving, the sensor going stale or
recovering, and an audit failure. Alerts are edge-triggered and deduplicated
— a persistent condition alerts once, not on every control tick. The dashboard
renders the latest alerts under an `alerts:` section, `/v1/metrics` exposes
them as `recent_alerts`, and the server mirrors each alert as a JSON line in
`alerts.jsonl` inside the installation directory for offline review. Alert
journaling runs inside the audit path: if the journal itself fails, the fault
latches exactly like any other audit failure.

`POST /v1/telemetry` requires the **camera** token and accepts a counts-only
feed whose body is exactly `{"counts": {"N": …, "S": …, "E": …, "W": …},
"conflict_clear": <bool>, "healthy": <bool>}`. It returns `202` with
`accepted_sequence` and feeds the same dashboard view as a full observation,
with the metric dictionaries empty (schema v1 semantics). It exists so a
counts-only sensor can drive the dashboard without implementing the extended
schemas; it does not bypass validation — counts are range-checked and the
sequence watermark still applies.

The local operator dashboard renders this snapshot in a terminal:

```bash
python -m sabz_edge.dashboard --directory data/local-installation
```

It reads the protected reader credential from the installation directory,
refreshes once per second and never places tokens in a browser URL. No cloud
service is in the dashboard path; the hot control path is unaffected.

Historical reports aggregate the local audit journal (observations,
transitions and preemption requests) without any network access:

```bash
python -m sabz_edge.report --database data/local-installation/edge.sqlite3 --since 24h
python -m sabz_edge.report --database data/local-installation/edge.sqlite3 --since 7d --json
```

`--since` accepts `90s`, `30m`, `24h`, `7d` or `all` (default). The text view
shows the window, event totals, per-approach vehicle averages, maximum wait
and pedestrian queue, stage dwell times and transition reasons; `--json`
emits the same summary for downstream tooling. Pedestrian flow analytics
break foot traffic down per approach (observations, total, average and peak
queue from schema v4/v5 pedestrian dictionaries) and report peak-hour foot
traffic — the densest rolling one-hour window of pedestrian demand in the
selected range. When schema v6 observations are present, a "stopped vehicles
by class" table shows per-class totals (car, motorcycle, bicycle, bus, truck)
and a per-approach class matrix, with the number of class-aware observations;
the table is omitted for journals that predate schema v6. The report also
derives idle and emission estimates: consecutive observations are spaced by
their `captured_at` stamps (gaps clamped to 60s), and each gap accrues the
observed stopped-vehicle queue as idle vehicle-seconds. With schema v6 class
data, per-class idle time converts to a rough CO2 estimate using fixed idle
factors (car 0.56, motorcycle 0.12, bicycle 0, bus 2.9, truck 3.5 g/s);
without class data the idle vehicle-seconds are reported as unclassified with
no emission figure. These are planning-grade estimates, not measurements.
The report only reads the
journal — it never touches the control loop.

Python producer:

```python
import os
from sabz_edge.client import CameraClient

client = CameraClient("https://edge.example.internal:8099",
                      os.environ["SABZ_CAMERA_TOKEN"])
try:
    client.send({"N": 12, "S": 8, "E": 2, "W": 1},
                conflict_clear=False, healthy=True)
finally:
    client.close()
```

`sabz_live.py` now publishes camera counts through this client. Its uncalibrated
camera cannot measure conflict-zone clearance, so it always reports false. It
will **not** release a bench green on counts alone. Add a validated clearance
sensor fusion producer before changing that assertion; do not infer clearance
from an empty vehicle count. The existing tracker remains an experimental
perception component and has no measured local-traffic accuracy claim.

## Timing, control and faults

Boot starts in all-red. A fresh healthy observation and positive clearance are
required before any green. Green serves one opposing pair only. After minimum
green, the baseline changes when opposing demand exceeds current demand by
the configured margin, or the current queue is empty while the other waits.
Maximum green bounds a healthy green even under continuous demand. Each change
passes through full yellow and full all-red. Clearance stays all-red while
the intersection is not reported clear. A busy intersection may therefore
prevent service indefinitely; safety takes precedence over a fairness claim.

Stale or unhealthy sensors terminate a green through yellow and hold all-red.
Sensor recovery can resume after clearance; audit/adapter failure, clock
regression or a control-loop overrun is latched and requires maintenance/restart.
No phase is driven by request counts. At most one state transition occurs per
tick; delayed execution cannot jump over a yellow or clearance interval.
Defaults in `config/bench-timing.json` are bench values, not road timing advice.

SQLite records accepted observations, transition intentions and acknowledged
emulator outputs as distinct event kinds, with full synchronous transactions.
An intention is not proof that the output was applied. Storage is rechecked for
elapsed time and sensor expiry before issuing a new command. Storage errors
inhibit new commands and latch a fault. If an acknowledgement audit fails after
an output, the independent cabinet expires the lease and performs clearance.
The local
journal is **not tamper-proof**, and can exhaust disk; monitor storage and export
to protected remote logging. Stop service for controlled retention maintenance;
retain replay watermarks. SQLite writer contention has a 100 ms busy timeout;
a genuinely blocked process/storage device cannot be recovered by its own loop.
The independent **bench** cabinet receives 0.5-second leases; loss of commands
or a disconnected edge process makes it complete yellow and hold all-red. That
fault cannot be reset by fresh commands. Readback queries do not renew a lease.
Status returns not-ready promptly when the control lock is blocked.

The cabinet uses 4 KiB-bounded JSON application messages; no application pickle
objects are deserialized from the pipe. It rejects malformed messages,
conflicting lamp maps, replayed commands and direct
green-to-conflicting-green changes, and enforces its own minimum green (with
fault termination), maximum green, yellow and all-red. It runs in a separate
spawned process with no database dependencies or network listener. The library's
basic `BenchAdapter` remains only an in-process unit-test fixture; the supported
CLI always uses `CabinetAdapter`.
The cabinet is spawned before SQLite is opened to avoid inheriting native
database handles through platform interpreter launchers. Failed database startup
also closes the cabinet and any opened resources.

This separation contains an edge-process stall; it is not a separate computer,
power supply or physical conflict monitor. A host failure can stop both processes.
A real cabinet must still provide independent local protection and readback.

## Road-cabinet adapter acceptance contract (not implemented)

Before adding an adapter, document the cabinet make/model, protocol and phase
mapping with the operator. This release deliberately exposes no hardware-enable
flag. A future adapter must provide:

- authenticated, ordered commands with short leases and restart/session identity;
- independent cabinet timing, mutually exclusive outputs and conflict monitoring;
- measured lamp/controller readback and acknowledgements, distinct from proposals;
- locally engineered fallback on lease expiry, disconnect, reboot and power loss;
- startup reconciliation with actual cabinet state and a physical/manual override;
- safe handling of pedestrians, turns and emergency movements at that junction.

The bench command includes an enforced process-local sequence and a 0.5-second
lease over an inherited local pipe. It is not a field transport protocol. Emulated
output is not physical readback. Test a future adapter using hardware-in-loop
fault injection before any road trial; do not wire this process to lamp relays.

## Validation and release gates

Run `python -B -m unittest discover -s tests -v`. Install `.[test]` to include
TLS certificate verification tests (the optional cryptography test dependency
generates disposable keys). Tests use loopback sockets and
temporary SQLite stores and disposable spawned processes. The suite includes
20,000 randomized controller steps and 50,000 hostile guard proposals, clearance
duration checks, stale sensor handling, request-time independence, durable replay
and capture regression rejection, concurrent duplicate submissions, slow HTTP,
header/framing limits, corrupt/full/contended storage, blocked audit, killed
parent processes, and whole-service kill/restart recovery.
These verify implementation properties within the two-phase bench scope;
they are not a formal proof or a collision-risk study. Run
`python -m examples.soak_verify` for the 130-second isolated-service bench soak
with maximum green, sensor health failure, feed loss and recovery. It records
emulated readback samples under `validation/soak-run.json`.

Next gates: calibrated labelled local footage; independent simulation with
held-out demand and pedestrians/turns; versioned model contracts and measured
baseline comparison; cabinet adapter and hardware-in-loop testing; independent
security review; traffic-authority timing and controlled trial approval.

References informing the design (not certifications or Pakistani legal approval):
[NIST SP 800-82r3](https://csrc.nist.gov/pubs/sp/800/82/r3/final) and
[FHWA signal timing background (archived)](https://ops.fhwa.dot.gov/publications/fhwahop08024/chapter5.htm).
