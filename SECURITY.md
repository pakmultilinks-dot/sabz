# Security scope and reporting

Supported integration surface: `sabz_edge`, `sabz_api.py`, and the observation
producer `sabz_live.py`. Other root scripts, browser demonstrations, trained
weights and videos are historical research artifacts, not field controllers.

The default service drives a separate-process emulator. An explicit low-voltage
ESP32-S3 bench path has a verified target build, but no flashing/electrical validation. It makes no claim of
certification, zero collisions, cyberwar resistance or compliance with all
traffic rules. See `docs/INTEGRATION.md` for the precise scope and release gates.

## Threat boundaries

| Threat | Implemented boundary | Remaining risk |
|---|---|---|
| Unauthenticated observation/feedback injection | Camera credential, no feedback/control endpoint | Stolen camera credential can fabricate observations |
| Network interception | TLS required off loopback; verified client TLS | Host/CA/key compromise |
| Replay and reordering | Persistent sequence and capture watermark, short capture-age window | Clock attack, restored old database, privileged maintenance |
| Malformed counts or payloads | Strict finite/type/schema checks, body limit | OS/network parser vulnerabilities |
| Request flooding | Bounded workers, absolute deadlines, header/body bounds and token bucket | Network exhaustion; gateway/firewall needed |
| Conflicting software outputs | Only two legal movement groups and explicit timed transitions | No physical interlock/readback implemented |
| Sensor outage/blocked intersection | Yellow then all-red; clearance required to release | A compromised sensor can falsely assert clearance |
| Model poisoning | No live learning/model loading in integration service | Research pipeline still needs validation |
| Hung edge process | Separate bench process expires leases and performs clearance | Host/power failure can stop both processes; physical protection required |
| Audit manipulation/exhaustion | Transactional local journal and fault latch | Privileged tampering, disk exhaustion and blocked I/O |

Bearer tokens are role credentials for one trusted producer and one reader,
not a fleet identity or PKI system. Keep services on a private OT network,
separate management access, restrict files and rotate credentials under
maintenance. Never reuse secrets among intersections. No remote maintenance
or shell execution endpoint exists. Do not expose the edge directly to the
public internet or pass tokens through query strings.

The independent bench cabinet is a fault-containment process on the same host,
not a separate privilege or physical safety boundary. Its application messages
are bounded JSON, not pickle. Compromise of the host or shared service account
can still tamper with both processes. Real deployment needs the cabinet's own
protected firmware, electrical interlocks, watchdog and readback.

Report security issues privately to repository maintainers through GitHub's
private vulnerability reporting if enabled. Otherwise request a private channel
without publishing exploit details or credentials in an issue. No security
contact address is invented by this release.


## Valid-but-dishonest sensor input: unresolved findings

The isolated audit in [ADVERSARIAL_SENSING_AUDIT.md](docs/ADVERSARIAL_SENSING_AUDIT.md)
reproduces hidden-demand starvation, false clearance and forged receiving-road
blockage using valid fresh packets. Maximum green bounds and software conflict
checks do not establish input truth, bounded red time or physical occupancy.
The report is `validation/dishonest-sensor-audit.json`. Security qualification
and road release remain blocked. Prior honest-demand simulation passes do not
close these findings. An independent electrical conflict monitor also cannot
substitute for independently validated physical-clearance sensing.
