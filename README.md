First hardware shopping and assembly: [docs/BENCH_SHOPPING_AND_ASSEMBLY.md](docs/BENCH_SHOPPING_AND_ASSEMBLY.md).

Local camera component and validation limits: [docs/CAMERA_SENSOR.md](docs/CAMERA_SENSOR.md).

Active algorithm contracts and remaining integration limits: [docs/ALGORITHM_INTEGRATION.md](docs/ALGORITHM_INTEGRATION.md).

Installation and operating instructions: [docs/INSTALLATION.md](docs/INSTALLATION.md). An ESP32-S3 low-voltage LED controller and serial adapter are implemented; board flashing and electrical validation remain unverified. See [physical bench guide](docs/PHYSICAL_BENCH.md). Road-signal integration remains unimplemented.

# SABZ — adaptive traffic edge integration

SABZ v0.1 provides a deployable edge service for integrating traffic observations
with a deterministic signal-controller **bench emulator in a separate process**. It has an authenticated,
versioned HTTPS API, persistent replay protection, an independently paced control
loop, timed phase transitions, audit storage and a camera producer SDK.

**Default output target: emulator.** An explicit low-voltage ESP32-S3 bench
adapter and successfully built firmware are available. This is not a certified
road controller and has no qualified road-cabinet adapter. It supports one intersection,
two opposing through-only phases and no turns. Pedestrian
demand is supported as a queue count (schema v4) and now serves a protected
walk: the walk accompanies the parallel vehicle green as a GREEN sub-state
(not a new cabinet stage), holds that green for at least `walk_min` (7s
default) against demand switches, extends with persistent demand up to
`walk_max` (20s default from green entry), reports reason `pedestrian_walk`
and `walk_active` in snapshots, and never skips yellow/all-red clearance —
safety exits (emergency preemption, sensor loss, maximum green) still end it.
Optional per-approach accessibility multipliers (1.0–3.0, for hospital/school/
senior crossings) proportionally extend walk and green durations on flagged
approaches without ever scaling yellow/all-red clearance.
Emergency preemption (schema v5) is an explicit
reader-authenticated request for one approach: it can end green early but
never skips yellow/all-red clearance, expires after 60 seconds and cannot
override a latched fault. It is not automatic emergency-vehicle detection.
The service reports `field_ready: false` explicitly.

## Start here

- [Adaptive controller and demonstration](docs/ADAPTIVE_DESIGN.md): deployed-system
  research, implemented decision rules, v2 inputs and reproducible comparisons.
- [Integration and deployment guide](docs/INTEGRATION.md): setup, API payloads,
  camera SDK, container deployment, timing/fault behavior and hardware contract.
- [Security scope](SECURITY.md): implemented defenses, trust boundaries and risks.
- [Release roadmap](docs/ROADMAP.md): perception, model evaluation, physical
  controller integration and field-pilot gates.
- [Hardware decision for Pakistan](docs/HARDWARE.md): ESP32-S3 physical bench
  target and integration with an authority-approved controller for a road pilot.
- [OpenAPI contract](docs/openapi.json): versioned machine-readable API description.

The supported edge package uses Python 3.11+ with no external runtime dependencies.
Run `python -m sabz_edge.server` after setting distinct `SABZ_CAMERA_TOKEN` and
`SABZ_READER_TOKEN` values of at least 32 characters. It defaults to loopback;
non-loopback binding requires a TLS certificate and key. See the guide for exact
commands. `python sabz_api.py` is an alias for the same service.

For a repeatable synthetic feed, run `python -m examples.bench_sender` with the
camera credential. This produces bench observations, including synthetic
conflict-zone clearance; it is not evidence from a real junction.

`python sabz_live.py traffic.mp4` publishes experimental YOLO camera counts to
the authenticated service. It deliberately cannot assert intersection clearance
from counts alone. Install camera dependencies separately; the edge service
does not need YOLO, OpenCV, NumPy, cloud access or an LLM.

For a local operator view, `python -m sabz_edge.dashboard --directory
data/local-installation` renders the live metric stream — per-approach counts,
approaching, arrival rates, health, sensor age, signal stage and recent
transitions — in a terminal. It reads the protected reader credential from the
installation directory; no cloud service is in the path. A counts-only sensor
can feed the same view with `POST /v1/telemetry`. For historical analytics,
`python -m sabz_edge.report --database data/local-installation/edge.sqlite3
--since 24h` summarizes the local journal — observations, stage dwell,
transition reasons, waits and preemptions — as text or `--json`.

## Verify

```text
python -B -m unittest discover -s tests -v
```

Tests cover timed transitions, 20,000 randomized controller steps, 50,000 guard proposals, stale data,
request-frequency independence, validation, durable replay rejection, role
separation, SDK integration, malformed/slow HTTP, storage faults, killed processes,
and service restart. Loopback networking is
required. CI is configured for Windows/Linux and Python 3.11–3.13.
These checks establish bench implementation behavior, not collision prevention.
Run `python -m examples.verify_release` for a 25-second real-time end-to-end
check that records synthetic bench evidence under `validation/bench-run.json`.
Run `python -m examples.soak_verify` for a 130-second isolated-service soak with
maximum-green enforcement, unhealthy sensors, feed loss and recovery.

## Research archive

Historical simulation, DQN models, presentations and browser demonstrations
remain available for research. They are not the supported integration path.
The DQN has known training/architecture inconsistencies and is not loaded by
the edge release. No new model-performance claim is made.

## Signal Lab

The private hosted Signal Lab is maintained in the dedicated `showcase` Sites
checkout. It animates paired simulations and can run fresh seeds/demand settings
using the same Python policy, safety kernel and cabinet model in a browser
worker. This is explicitly synthetic simulation, with no road-controller link.
The benchmark includes 105 controller runs and displays regressions as well as
improvements. Generate evidence with `python -m examples.build_showcase`.
The supported API accepts strict v2 traffic observations for the advanced
controller; v1 remains the legacy queue-actuated path.

[Archived research README](docs/LEGACY_RESEARCH.md) records previous claims for
traceability. Its accident-prevention guarantees, performance figures and
training status are historical and unverified for this release. Its relative
asset links refer to the original repository root. See the release roadmap for
what must be measured before making new product claims.
