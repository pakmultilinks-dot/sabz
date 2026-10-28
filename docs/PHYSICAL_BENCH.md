# Physical low-voltage controller: build and acceptance guide

This is the first physical-I/O implementation for SABZ, targeting the official
ESP32-S3-DevKitC-1 board. It is a six-LED, two-through-phase engineering bench,
not a road cabinet. Do not connect mains, road heads, relay modules or another
controller's outputs to these GPIOs. No ESP32 board is connected to the current
development computer, so no flash, electrical or physical lamp test is claimed.

## Delivered code and verified scope

- `firmware/esp32s3_bench/bench_core.h`: bounded C++ parser and timed controller.
- `firmware/esp32s3_bench/esp32s3_bench.ino`: GPIO, local inputs, UART and watchdog.
- `sabz_edge/serial_bench.py`: serial framing, boot/session binding and ACK checks.
- `sabz_edge/hardware_bench.py`: explicit opt-in service using that serial adapter.
- `tests/test_firmware.py`: compiles and executes the SAME C++ core on the PC;
  exercises the Python adapter through a compiled-process byte transport.

The shared C++ core is compiled/tested natively. The actual ESP32-S3 target
also builds successfully with Arduino CLI 1.5.1 and Espressif core 3.3.0, using
`esp32:esp32:esp32s3`. Flashable artifacts are in
`data/firmware-release/esp32s3_bench`; source/artifact hashes and logs are in
`validation/esp32-build-manifest.json`, `validation/esp32-target-build.txt` and
`validation/esp32-rebuild-manifest.json`. The repeatable local build command is
`./deploy/build_firmware.ps1`. The pinned core is a build baseline, not a claim
that it is the latest security-qualified SDK.

The build uses 309315 bytes of program storage and 20720 bytes of static RAM.
One vendor-core legacy touch API deprecation warning was emitted. No board has
been flashed. GPIO behaviour, watchdog operation, USB/UART timing, reset/power
behaviour and actual pins still require electrical bench testing. Native byte
transport fixtures are not electrical hardware-in-loop evidence.

## Parts for this exact bench design

Use an ESP32-S3-DevKitC-1 matching the vendor pin labels; six discrete LEDs
(two red, two amber, two green); one 1 kOhm series resistor per LED; six
100 kOhm pull-down resistors; a breadboard/jumpers; a data-capable USB cable;
and a normally-closed stop switch. A labelled clearance switch is for deliberate
manual bench assertion only. Prices, local stock and alternate board pinouts
have not been verified. Do not substitute a road-signal module for an LED.

| GPIO label | Function | Connection with power OFF |
|---|---|---|
| 4 | NS red | GPIO -> 1 kOhm -> LED anode; cathode -> GND |
| 5 | NS amber | Same LED/resistor arrangement |
| 6 | NS green | Same LED/resistor arrangement |
| 7 | EW red | Same LED/resistor arrangement |
| 8 | EW amber | Same LED/resistor arrangement |
| 9 | EW green | Same LED/resistor arrangement |
| 10 | Local clearance | Normally open switch to GND; LOW explicitly asserts clear |
| 11 | Stop healthy loop | Normally closed switch to GND; open/HIGH latches stop |

Put one 100 kOhm resistor from each output GPIO to GND, in addition to its
series LED resistor. This biases outputs off while GPIOs float. Pins 10 and 11
use internal pull-ups, so disconnected inputs do not grant clearance or a
healthy stop loop. Check LED polarity and resistor values before powering.
These six LEDs represent two signal GROUPS, not six independent road movements.

Use only the board's supported USB power arrangement. The vendor lists supply
options and warns that alternative supply methods are mutually exclusive.
Do not improvise mixed USB/5V/3V3 power wiring. If the USB cable supplies all
power, unplugging it makes the LEDs dark: the watchdog cannot run without power.
Testing link loss with a powered board requires a supported independently powered
arrangement; killing the edge process is a separate software-link test. Brownout,
reset and power-off are NOT proven all-red physical states. A road controller
needs a genuinely independent safety/power design.

Vendor references: [board pin and power guide](https://documentation.espressif.com/api/resource/path/docs/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide.html),
[Arduino-ESP32 installation](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html).
These references support board setup, not traffic-controller qualification.

## Build before wiring outputs

Use Arduino IDE/CLI with Espressif's Arduino-ESP32 3.x platform (ESP-IDF 5.x).
The provided CI job specifies the same 3.3.0 reproducibility baseline that
passed the local ESP32-S3 target build. Remote CI has not been run here. With Arduino CLI installed:

```sh
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32@3.3.0 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli compile --fqbn esp32:esp32:esp32s3 firmware/esp32s3_bench
arduino-cli board list
```

Resolve any compiler errors and save the build log before proceeding. Select the
actual enumerated board port; do not guess COM numbers. Upload with the LEDs
initially disconnected:

```sh
arduino-cli upload --fqbn esp32:esp32:esp32s3 --port COM4 firmware/esp32s3_bench
```

`COM4` is an example, not a detected device. The sketch uses `Serial` at 115200.
With default board settings use the USB-to-UART connector. Close any Serial
Monitor before attaching the Python adapter. Reconfirm build options if selecting
native USB CDC instead; that path has not been tested.

Close the stop loop BEFORE reset/power-up. The open loop intentionally latches a
fault and requires local reset after correcting it. Start with clearance open;
the device must show both reds and refuse green. Use a meter to verify GPIO
levels against the intended pin map before attaching LEDs.

## Connect SABZ to the board

From the repository root install the optional serial transport:

```powershell
python -m pip install '.[hardware]'
python -m serial.tools.list_ports
```

Use a separate state directory and listener from the already-running emulator:

```powershell
New-Item -ItemType Directory -Force data/hardware-bench | Out-Null
$env:SABZ_BIND = '127.0.0.1'
$env:SABZ_PORT = '18100'
$env:SABZ_STATE_PATH = Join-Path $PWD 'data/hardware-bench/edge.sqlite3'
$env:SABZ_CAMERA_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
$env:SABZ_READER_TOKEN = python -c "import secrets; print(secrets.token_urlsafe(32))"
Remove-Item Env:SABZ_TIMING_FILE -ErrorAction SilentlyContinue
Remove-Item Env:SABZ_TLS_CERT -ErrorAction SilentlyContinue
Remove-Item Env:SABZ_TLS_KEY -ErrorAction SilentlyContinue
python -m sabz_edge.hardware_bench --port COM4 --low-voltage-bench-only
```

The explicit switch acknowledges this LOW-VOLTAGE bench scope. It is not a field
activation switch. Firmware profile 1 fixes min/max green/yellow/all-red to
8/60/3/2 seconds; the adapter rejects a different timing profile. The normal
`sabz_edge.server` command continues using its emulator. A failed serial adapter
never silently substitutes the emulator. Hardware mode still has `field_ready`
false and no certification claim.

The firmware's local clearance input AND the sensor observation's clearance must
allow release. Do not close the clearance switch and publish clear=true as a
substitute for an actual road sensor. Fabricated traffic is acceptable only for
this explicitly isolated LED acceptance bench. To connect actual perception,
use the existing authenticated CameraClient protocol; metric sensing remains
uncalibrated/unimplemented and is a separate development task.

## Controller protocol and security boundary

ASCII lines are at most 128 bytes, 115200 baud, LF terminated. CRLF replies are
accepted by the Python adapter for native Windows transport compatibility.
Format is `payload*crc32hex` plus newline; CRC is IEEE/zlib CRC32, lowercase hex.

- Command: `C,boot16hex,sequence,stage,phase,fault_request,lease_ms`
- Query: `Q,boot16hex` (never renews the lease)
- Reply: `R,boot16hex,sequence,stage,phase,fault,gpio_bits,board_ms`

Stage: 0=all-red, 1=green, 2=yellow. Phase: 0=NS, 1=EW. Sequence is increasing
unsigned 32-bit, nonzero; exhaustion requires planned local restart. A board
boot changes the 64-bit session identifier. Automatic reattachment to a rebooted,
already commanded or faulted board is disabled. Boot ID is not authentication.
Lease is 100..500 ms; the host normally sends at a 20 Hz target. A partial frame
expires after 100 ms. The board processes at most 64 input bytes per loop.

Fault codes: 1 bad frame, 2 wrong session, 3 replay, 4 lease lost, 5 conflicting
phase request, 6 stop-loop/watchdog-setup failure, 7 output-level mismatch.
Faults latch until local reset. A fault during green starts yellow; the full
yellow then all-red elapses independently of the PC. A task watchdog is requested
with 2-second timeout. Watchdog reset does not preserve an active yellow through
reboot; this is one reason the board is not a qualified road safety controller.

CRC detects transmission corruption; it does not authenticate an attacker.
A person with access to USB/serial or the PC can submit valid phase proposals or
cause denial of service. Secure boot, encrypted/keyed messaging, production key
provisioning, protected firmware updates and an independent electrical conflict
monitor are NOT implemented. No Wi-Fi or remote update service is started by
this sketch. Do not describe this prototype as cyberattack-proof.

Readback samples GPIO logic levels via the input/output GPIO configuration.
It cannot prove LED current, emitted light, wiring correctness, lamp driver
health or an external relay state. `physical_lamp_verified` is always false.
A native test transport labels `physical_hardware` false. Actual serial mode
labels board I/O physical, while retaining the readback limitation.

## Physical acceptance: execute and record results, do not assume pass

1. Startup/reset: both red indicators; all green/amber indicators off. Observe
   reset/power-off separately and record the dark interval; do not call it all-red.
2. Clearance open: no green, even with healthy host demand. Close clearance only
   after deliberately confirming the empty bench conflict zone.
3. Normal traffic changes: minimum green, full yellow and clearance measured with
   timestamps and external GPIO capture, not just the host's requested stage.
4. Continuous same-phase requests: local max green forces yellow at 60 seconds.
5. Stop loop: open during green; board enters yellow then all-red and latches.
6. Stop/kill the producer and edge separately: sensor loss follows the kernel's
   sequence; edge loss expires the board lease. Queries must not keep green alive.
7. Wrong boot ID, repeated sequence, bad CRC, truncated/oversized frames and direct
   opposing green: reject/fault; never conflicting green outputs.
8. Reset, cable removal and power changes: record observed electrical levels and
   recovery. Reattachment requires local healthy reset; no unobserved resume.
9. Compare readback with independent GPIO measurement. Test actual LED/light
   detection only after adding an external current/light measurement circuit.

Native tests cover core logic, selected malformed inputs, host framing and clock
wrap. They do not close these physical acceptance items. Record equipment model,
board revision, firmware hash, build log, wiring checks and every pass/fail result.
Stop testing on unexpected outputs, correct the cause and repeat affected cases.

## Required metric interlock

`python -m sabz_edge.hardware_bench` now forces required metric protection.
Count-only schemas 1/2, missing metrics and metrics older than 200 ms cannot
release a green. Loss during green initiates yellow/clearance, including before
normal minimum green where the sensor-fault path applies. Post-audit expiry
is also rechecked before commands are issued. Emulated legacy research remains
explicitly unprotected unless this timing requirement is enabled. This software
interlock is not independent protection against a compromised host and does not
make the bench suitable for road operation. See COMMERCIAL_READINESS.md.
