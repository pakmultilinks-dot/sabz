# Product release gates

## Delivered in v0.1 — bench integration

- Standalone standard-library edge package, SDK, CLI and container recipe.
- Versioned authenticated observation API with network TLS enforcement.
- Deterministic timed two-phase controller; no model or arbitrary lamp endpoint.
- Persistent sequence replay protection, journal and single-process ownership.
- Independent-process bench cabinet with enforced leases, acknowledged emulated
  readback, kill/stall/storage/HTTP fault tests and CI configuration.
- Experimental live camera producer routed through the same API.

## Next — measured perception and honest algorithm comparison

Select a representative local junction and obtain authorized footage. Annotate
held-out clips, calibrate lanes/stop lines and conflict zones, measure counts
and tracking quality including motorcycles/occlusion/night conditions. Add
sensor confidence, independent occupancy where available, and measured
downstream capacity. Counts alone are not an intersection-clear signal.

Validate movement topology, pedestrians/turns and engineering timing in an
independent simulator. Benchmark a tuned fixed plan, actuated baseline,
pressure-based control and a trained candidate on identical pre-generated
arrival traces, separate noise seeds and held-out scenarios. Include throughput,
mean/tail delay, maximum wait, unresolved queues and fault behavior. Publish raw
traces and uncertainty, not just a winning percentage from three seeds.

The legacy NumPy DQN training code is not repaired or used by this release.
Known blockers: BC forward-cache mismatch; incompatible saved architectures;
inconsistent live-state normalization; school benchmark time-window mismatch;
automatic partial-weight transfers; and promotion using repeatedly reused test
scenarios. Fix and test those before running an expensive training job. Require
strict state/weight metadata, hashes, independently held-out promotion criteria
and rollback. A trained model can only propose within the safety kernel.

## Next — physical bench

Obtain the intended controller make/model and protocol specification. Build a
cabinet adapter with independent timing/interlocks, command acknowledgement,
lamp readback, physical override, restart reconciliation and lease-expiry local
fallback. Test host hangs, cable pull, spoofed commands, blocked I/O, reboot and
power loss. Do not use an unmonitored relay board as a field controller.

## Field pilot gate

Traffic-authority review of the actual junction and timings, pedestrian and
turn handling, licensed hardware as required locally, independent security and
hazard review, authorized shadow operation, operator training, incident response
and approved controlled trial. No repository test can substitute for these.
