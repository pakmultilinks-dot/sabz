# Commercial release status and safety responsibilities

Status: BLOCKED for paid public-road operation. SABZ is an engineering prototype
with a working software control path and an unverified low-voltage board target.
No claim of certification, authority acceptance, cyberattack immunity, accident
prevention or guaranteed latency is justified. A successful installation command,
passed software tests or customer payment cannot change this status.

## Safety change delivered in this revision

The explicit `hardware_bench` startup now forces `require_metric_protection=True`.
A legacy count-only packet or metric data older than 200 ms cannot release green.
Loss during green requests yellow, followed by full clearance. A post-audit
freshness check prevents issuing a green after disk I/O consumes the metric
freshness budget. Runtime readiness also withdraws when required metrics expire.
The independent emulator and serial-to-compiled-C++ path recognize this sensor
fault as eligible for early yellow, without skipping yellow or clearance.

Default emulated legacy experiments retain optional metric protection for
backward-compatible research. That unprotected profile is not a field fallback.
The physical bench command cannot disable the requirement through its timing
file. This interlock is host software, not independent assurance against a
compromised host or forged measurements. Loss of the host itself still invokes
the board's separate lease; the combined detection/lease/clearance timelines
require physical measurement and site engineering.

## Hazard register: current residual blockers

| Hazard | Existing mitigation/evidence | Residual work before commercial road release |
|---|---|---|
| Opposing green outputs | Timed kernel, independent process and C++ controller tests | Independent electrical conflict monitor, fault insertion and qualified cabinet |
| Stale/missing approach metrics | Required-metric interlock, audit-time recheck, guard/serial regression tests | Measured physical deadline and approved fallback behaviour |
| False/occluded detections | Survey math, track health checks, bounds and expiry | Local labelled data, adverse conditions, calibrated uncertainty and independent clearance sensing |
| Host/sensor compromise | Roles, TLS, replay limits, constrained outputs | Threat model review, authenticated device lifecycle, protected updates/configuration, independent local safety boundary |
| Serial spoofing | CRC/session/sequence detect accidental corruption and stale commands | CRC is not authentication; production transport, key lifecycle and physical access design |
| Power loss/reset | Board startup logic and watchdog source code | Power-independent protection; bench USB power loss makes LEDs dark; reset does not preserve yellow |
| Overload/starvation | Bounded allocation, phase opportunity tracking, scenario matrix | Validate performance and road-user equity on the actual movement plan; no promise to clear excess demand |
| Scheduling/storage delay | Deadline/expiry checks, instrumentation and fault tests | Hard timing assessment; earlier 1.17 s first-sample outlier remains unexplained |
| Privacy/data misuse | Metric bridge emits aggregates, not frames/track identities | Document actual detector retention/access, permissions, incident handling and deployment-specific review |
| Unsupported movements | Explicit two-phase through-only scope and fifth-approach rejection | Design/validate turns, pedestrians, emergency/rail interaction as required by the chosen site |

The table is a preliminary engineering register, not a completed safety case,
FMEA or independent security assessment. Required evidence must be reviewed by
people competent in traffic engineering, electrical/control safety and OT
security. Responsibilities and acceptance criteria must be agreed with the
actual operating authority/customer, not inferred from foreign product brochures.

## Evidence required for release

1. Versioned operating requirements and a supported movement/conflict matrix.
2. Hardware/interface selection, electrical drawings, readback semantics,
   approved timing envelope, manual override and fallback definitions.
3. Measured detection/tracking/calibration quality on authorized local footage
   across motorcycles, crowding, weather, darkness and occlusion.
4. Reproducible target firmware build, provenance/hash, flashing record and
   hardware-in-loop acceptance with independent output measurement.
5. Security assessment covering credential theft, valid-but-malicious sensors,
   replay, resource exhaustion, update compromise, physical access and recovery.
6. End-to-end latency/deadline and endurance evidence, including capture, I/O,
   host scheduling and actual controller/lamp readback. Software ACKs are insufficient.
7. Site commissioning/rollback tests, configuration inventory and operator training.
8. Operations ownership: support coverage, alarms, maintenance, audit retention,
   tested backups, patch/change control and incident response.
9. Written review of applicable approvals, privacy obligations, liability and
   commercial terms by the responsible local professionals/parties. No such
   legal/financial assessment has been completed in this repository.

A release review must distinguish evidence that exists from planned tests,
identify unresolved high-severity hazards, and keep road output disabled until
those hazards and the required site acceptance are addressed. `field_ready`
remains false. The current `preflight --require-field-ready` deliberately fails.

## Commercial scope communication

A demonstration or R&D engagement must describe the delivered scope accurately:
software prototype, synthetic tests, native C++ controller tests and unverified
ESP32 target/electrical operation. Do not describe it as an installed traffic
controller, comprehensive edge-case proof or a nationally deployable product.
Performance results apply to the tested configuration and conditions only.
Any pricing/support commitment needs a separately agreed deliverable scope and
cost model; local hardware prices, maintenance costs and procurement eligibility
have not been verified. No production quotation is supplied by these artifacts.
