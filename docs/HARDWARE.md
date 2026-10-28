# Hardware decision for Pakistan

Decision (2026-10-26): use an ESP32-S3 development board for the low-voltage
physical demonstrator, an existing laptop/mini PC for vision and edge software,
and an authority-approved traffic cabinet for any future road pilot. Do not
purchase a replacement road controller before identifying the pilot junction's
existing cabinet and the responsible authority's requirements.

## Physical demonstrator target

- ESP32-S3 development board using ESP-IDF; USB/UART link to the edge computer.
- Four low-voltage red/amber/green LED signal heads, appropriate resistors and
  driver circuitry. No mains-powered traffic heads or road relays.
- Local all-red/manual-stop input and labelled sensor-fault/clearance inputs.
- Controller firmware owning the transition sequence and watchdog independently
  of the vision computer; no arbitrary per-lamp writes from the AI.
- Separate readback/acknowledgement channel and deliberate cable-pull/reboot tests.

A first ESP32-S3-DevKitC-1 low-voltage firmware and serial adapter are now
implemented. The shared C++ core is compiled/tested natively, and the ESP32-S3
target build passes. Flashing and electrical checks remain unverified. See
[PHYSICAL_BENCH.md](PHYSICAL_BENCH.md) for the exact LED pin map, protocol,
limitations and acceptance procedure. Default service output remains emulated.
Do not assume GPIO boot levels or available pins across different board variants.

The S3 supports secure boot, flash encryption and HMAC according to
[Espressif's product documentation](https://www.espressif.com/en/products/socs/esp32-s3),
and includes hardware watchdogs documented in the
[datasheet](https://documentation.espressif.com/esp32-s3_datasheet_en.pdf).
These are useful bench-development features, not traffic safety certification.
Secure boot must be deliberately provisioned; simply using this board does not
enable it. Physical attack resistance also needs review: see the vendor's
[2026 voltage fault-injection advisory](https://documentation.espressif.com/AR2026-005_Security_Advisory_Concerning_AES_Key_Recovery_Using_Voltage_Fault_Injection_on%20ESP32-S3_EN.html).

## Pakistan field integration target

Use an edge appliance at the junction to process authorized camera feeds and
propose bounded signal changes to the existing controller through its documented
interface. The cabinet retains local timing, conflict protection and operator
control. Cabinet protocol, electrical isolation, readback and fallback must be
verified on the actual equipment; do not assume every cabinet speaks NTCIP,
Modbus or generic HTTP.

This approach matches the need to integrate with existing infrastructure:
[PSCA describes centralized traffic-signal connectivity](https://psca.gop.pk/ptms/),
and a [PSCA signal-timer procurement document](https://psca.gop.pk/wp-content/uploads/2021/03/PPRA-Upload-BD-Signal-Timers.pdf)
specifies compatibility with an urban traffic controller. These references do
not establish an open API, identify the controller at our eventual junction, or
authorize access. Coordination with the authority is a required pilot gate.

Before buying field hardware, obtain: target junction and authority; cabinet
make/model, firmware and documented integration protocol; movement/phase plan
including pedestrians and turns; approved timings; power/UPS and environmental
requirements; camera placement; and authorized private-network access.

Local component availability and prices have not been verified. Reuse the
existing computer first and procure only the low-voltage bench parts after the
board/module variants are confirmed. Measure vision latency on actual footage
before choosing the field edge-computer specification.
