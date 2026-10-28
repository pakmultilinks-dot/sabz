# Validation record — 2026-10-27

Scope: synthetic two-phase software bench. No physical lamps, real-junction
video, trained policy, pedestrian movements or road trial were used.

## What was tested

- Deterministic phase timings and 20,000 randomized controller steps.
- 50,000 hostile cabinet proposals: conflicting lamps, direct phase changes,
  replayed commands, leases and latched faults.
- Separate cabinet process: stalled parent, killed parent, cabinet death,
  malformed/non-JSON IPC, and blocked audit storage.
- Real HTTP/HTTPS: role separation, trusted/untrusted certificates, body/header
  and URL bounds, ambiguous framing, absolute slow-client deadlines, connection
  saturation and concurrent duplicate observations.
- Persistence: watermark survival after service kill/restart, older capture
  rejection, SQLite contention, simulated disk-full rollback and corrupt startup.
- Clean installed-wheel execution outside the source checkout with Python `-I`;
  installed package SHA-256 hashes checked against the source.
- A real-time 25-second integration demonstration and a 130-second isolated
  service soak: maximum green, unhealthy camera, feed loss and recovery.

The ordinary suite and installed-wheel suite each passed all 58 tests. Raw result logs
are [source-tests.txt](source-tests.txt) and
[isolated-wheel-tests.txt](isolated-wheel-tests.txt). TLS tests were included,
not skipped. Tests run on Windows, Python 3.11.9.
The installed service's forced-kill/restart test was also repeated separately;
see [restart-repeat-tests.txt](restart-repeat-tests.txt).

## Findings fixed during this review

| Finding | Correction |
|---|---|
| A blocked audit/control owner could leave the original emulator at its last output | Separate cabinet process expires commands and completes its own clearance |
| Leases were advertised but not independently enforced | Independent 0.5-second lease, local timers, acknowledged emulated readback |
| Very large JSON integers raised OverflowError and faulted the service | Range check before floating-point conversion; invalid observations return 400 |
| A new sequence could replace a newer observation with an older capture | Persistent capture watermark in addition to sequence watermark |
| A slow audit could issue a decision after sensor expiry | Recheck elapsed time and freshness immediately before command issuance |
| Timer origin could precede delayed command issuance | Commit transition timing at issuance; independent cabinet enforces actual durations |
| Socket inactivity limits did not bound continuously trickled headers | Absolute connection deadline plus aggregate header and request-line limits |
| Unknown routes bypassed the request bucket | Central request admission after parsing |
| Corrupt SQLite startup leaked its file handle | Close failed initialization before propagating the error |
| Ambient proxies could intercept or delay SDK connections | Explicit direct connection policy; proxy and redirect regression tests |
| Intent logs could be mistaken for executed output | Separate transition-intent and acknowledged-output event kinds |
| Early POST errors could reset Windows TCP before clients received the response | Bounded discard of unambiguously framed body bytes before closing; repeated early-error regression checks |
| Application IPC used Python object serialization | Bounded JSON messages; malformed-message and non-JSON rejection tests |
| An installed-Windows restart test exposed file-handle lifetime uncertainty | Spawn the cabinet before opening SQLite; tests launch the actual interpreter instead of a venv redirector, and repeat forced restarts |

These are reproduced implementation findings and scoped corrections. The
randomized cases are finite test inputs, not exhaustive proof of all states.

## Adaptive Signal Lab

The private hosted demonstration runs the same Python kernel, adaptive policy
and cabinet model in a browser worker. A new seed (2026) and demand multiplier
(1.2) were computed in the browser: visible final delays were 52.9 seconds fixed,
14.1 actuated and 15.6 adaptive, matching native Python at display precision.
This particular fresh run is also a regression against actuated control; it is
not hidden.

The synthetic adaptive benchmark covers 105 controller runs (seven scenarios,
five seeds, three controllers) and includes all regressions. The policy improved
on actuated in six of seven scenario averages and on fixed timing in four of
seven. See adaptive-benchmark.json and docs/ADAPTIVE_DESIGN.md.

Publication was verified by the native Sites deployment status. Browser testing
of the full UI and live computation was local; the hosted URL correctly showed
an account sign-in gate, so authenticated hosted computation was not inspected.
No credentials were entered or private access bypassed.

## End-to-end evidence

[bench-run.json](bench-run.json) records requested outputs alongside separately
acknowledged cabinet state and the independent cabinet's transition trace.
[soak-run.json](soak-run.json) records the isolated service's sampled readback,
readiness, reasons and sensor age. Both use explicitly synthetic observations.
The soak must observe maximum-green termination, not-ready status during the
injected camera/feed failures and readiness after recovery; conflicting active
movement groups or unexpected controller/cabinet faults fail the run.
Times in producer reports are relative to the producer run, after service startup;
the service/cabinet timing checks also run independently in the test suite.

`build-manifest.json` records source/test/example hashes and the host runtime.
No credential is included in the evidence files. Disposable service listeners,
producer state and test databases are closed after successful runs.

## Reproduce

```text
python -B -m unittest discover -s tests -v
python -m venv .venv-edge-test
.venv-edge-test/Scripts/python.exe -m pip install ".[test]"
python -m examples.verify_installed --python .venv-edge-test/Scripts/python.exe
python -m examples.verify_release
python -m examples.soak_verify
```

On Linux, use the virtual environment's `bin/python` path instead. Tests were
configured in CI for Windows/Linux and Python 3.11–3.13, but this work has not
run the GitHub CI matrix.

## Remaining limits and confidence

The tested software bench has materially stronger evidence than the initial
prototype. It is ready for further bench integration within the documented scope.
It is **not ready to control a public-road junction**.

Linux container execution remains unverified: Docker Desktop was asked to start,
but no Linux engine became available; a subsequent stop request also failed.
The stalled CLI launchers were stopped. The image was not built or run locally.
Compose configuration parsing passed. Docker Desktop may require local repair.

There is no claim of all-edge-case coverage, formal verification, penetration-test
certification, continuous multi-day availability or collision-risk reduction.
The two processes share a host and user account; they do not protect against a
compromised OS, shared power loss or privileged code tampering. They are not a
physical conflict monitor. Perception accuracy, trained-model performance,
pedestrians/turns, actual cabinet integration, electrical failure modes and
traffic-authority approval remain open release gates in docs/ROADMAP.md.
