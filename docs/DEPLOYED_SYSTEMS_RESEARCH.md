# SABZ: deployed-system research and completion requirements

Research date: 27 October 2026. Sources below are government/transport authority
or original vendor publications. Older engineering references inform design;
they do not establish Pakistani approval, current local procurement eligibility,
or compatibility with a particular controller. Vendor performance claims are
not treated as SABZ performance evidence.

## 1. What established systems actually supply

**SCATS:** the adaptive software adjusts cycle length, movement time allocation
and offsets using detector measurements and pedestrian requests. Its TRAFF
controller firmware handles local phases, safety functions and communication.
Approved controller partners supply compatible hardware. Deployment services
include controller-personality configuration, integration, implementation and
traffic modelling; support includes maintenance agreements, training and
troubleshooting. This is a combined software, compatible hardware, engineering
and support delivery, not simply a trained vehicle-counting model.

Sources: [SCATS Core brochure](https://www.transport.nsw.gov.au/system/files/media/documents/2022/SCATS-Core-brochure-Final-web-spreads.pdf),
[controller partners](https://scats.nsw.gov.au/partners),
[services](https://www.scats.nsw.gov.au/solutions/services),
[support](https://www.scats.nsw.gov.au/support).

**SCOOT:** regularly adjusts splits, cycle length and offsets using measured
traffic and predicted flows. Yunex describes an integrated offer spanning
on-street equipment, adaptive software and central/regional management. Its
FUSION paper describes model-based optimization of road-user delay/stops and
a 15-junction London Living Lab for development and validation. Public product
summaries explain architecture, not a complete implementation or proprietary
source code. We cannot claim to reproduce either product from their brochures.

Sources: [SCOOT product](https://us.yunextraffic.com/portfolio/adaptive-technologies/scoot/),
[FUSION engineering paper](https://www.yunextraffic.com/wp-content/uploads/2024/04/Yunex-Traffic_Fusion_Paper_EN.pdf).

## 2. How a system becomes a completed delivery

FHWA distinguishes verification (does the delivered system meet specified
requirements?) from validation (does it achieve the agency's operational
objectives?). Measures include travel time, delay, throughput, queues and access
equity. Its testing handbook progresses from component tests through hardware
and software integration to operational acceptance. Installation records,
configuration, calibration, documentation and trained operators matter alongside
the software. Passing local unit tests cannot substitute for those activities.

Sources: [adaptive validation framework](https://ops.fhwa.dot.gov/publications/fhwahop13031/chap1.htm),
[integration and acceptance testing](https://ntlrepository.blob.core.windows.net/lib/26000/26500/26507/chapter_4.htm),
[site acceptance](https://ntlrepository.blob.core.windows.net/lib/26000/26500/26507/chapter_6.htm).

Recommended SABZ delivery sequence (our engineering proposal):

| Step | Deliverable | Evidence needed to close it |
|---|---|---|
| Operating requirements | Supported intersection layouts, road users, objectives, exclusions, fault behaviour | Reviewed requirements with measurable pass/fail criteria |
| Site/controller definition | Movement conflict matrix, documented controller interface, approved timing envelope | Interface documentation and engineering review; no guessed relay mapping |
| Sensing | Calibrated local vehicle/queue/speed measurements and conflict-zone sensing | Independently labelled local data, error/coverage results, health detection |
| Physical integration | Controller adapter, electrical readback, local fallback and override | Hardware-in-loop commands/readback and injected failure traces |
| Security | Device identity, network boundaries, update/recovery procedures | Threat model, independent review and adversarial verification |
| System qualification | Complete integrated configuration and known limitations | Traceable acceptance report, latency measurements and endurance results |
| Installation/commissioning | Site configuration, calibration, rollback and operator handover | Site acceptance signed by responsible parties |
| Performance validation | Comparison against a properly configured baseline | Matched demand/conditions, uncertainty, access-equity and congestion results |
| Operations | Monitoring, maintenance, backups, updates and support ownership | Exercised procedures and maintained configuration inventory |

These stages cannot all be completed by code running on this development PC.
They require equipment, authorised site access and traffic/electrical expertise.
No numerical completion percentage or calendar estimate is justified yet.

## 3. Architecture SABZ should target

Dedicated authorized local camera/radar/loops -> local perception and health
checks -> bounded adaptive timing proposals -> documented traffic-controller
interface -> local signal controller -> independent physical conflict protection
and measured readback.

The operator/management service provides configuration, alarms, inventory,
aggregate metrics and maintenance. It does not need national raw-video streaming
or a cloud round trip for every signal decision. This is our proposed architecture;
it is not a statement that every deployed product uses exactly this topology.

For an initial commercial product, integrate with an accepted controller rather
than attempting to manufacture and qualify an entire roadside cabinet at once.
This is an engineering scope recommendation, not a claim that an available
Pakistani cabinet exposes a suitable interface. A low-voltage microcontroller
fixture remains a development tool, not a qualified replacement controller.

## 4. The 70-metre feature needs a stronger safety definition

FHWA's D-CS implementation guide uses estimated arrival/departure times and
vehicle information to choose a phase termination opportunity; it also retains
a maximum green. A fixed distance alone does not describe the dilemma zone
across different speeds. Its numerical examples and time windows concern the
studied high-speed application, not a universal setting for Pakistan.

SABZ currently uses a bench 70 m / 6 s rule with aggregate minimum distance and
maximum speed. Those aggregates can combine different vehicles, and the rule
does not model braking, slope, vehicle length or trajectory uncertainty fully.
It must not be advertised as validated accident prevention. Maximum termination
can still catch an approaching vehicle; correctly engineered yellow/clearance
and sensor coverage remain necessary. A moving vehicle near the junction must
not disable cross-road service indefinitely.

Source: [FHWA D-CS implementation guide](https://www.fhwa.dot.gov/publications/research/safety/14058/005.cfm).

## 5. Fallback is an operating mode, not only a software exception

FHWA's example adaptive requirements include detector substitution/recall where
appropriate, alarms and user-specified time-of-day or local operation when
adaptive control cannot continue. The fallback depends on location and time.
This means loss of an optimization input need not imply indefinite all-red.
A physical conflicting-output fault is a different condition and requires the
cabinet's engineered protective response. The responsible engineer must define
the distinction; SABZ must not autonomously invent that plan.

Our current emulator performs yellow then all-red on faults. That is useful for
bench fault containment, but is not an approved operational fallback. Similarly,
expired metric observations currently leave an explicitly unprotected bench
scheduler; they must not silently disable a required road safety function.

Source: [FHWA failure scenarios](https://ops.fhwa.dot.gov/publications/fhwahop11027/ap_c.htm).

## 6. Cybersecurity and privacy requirements

NIST SP 800-82 Rev.3 is the final OT-security guide used here; Rev.4 is a draft
as of this research date. It addresses security together with OT reliability,
performance and safety. The proposed SABZ security work is to define trust
boundaries and asset ownership, segment sensor/control/management networks,
use unique device credentials, constrain commands locally, protect updates and
configuration, log security events and exercise recovery. These are design tasks,
not a claim of NIST certification or attack immunity.

SABZ's TLS, authentication and anti-replay checks address only part of this.
An authenticated compromised sensor can send plausible false measurements;
a compromised operating system can affect both current software processes.
Physical conflict protection must therefore be independent of the AI host.

Source: [NIST SP 800-82r3](https://csrc.nist.gov/pubs/sp/800/82/r3/final).

Privacy proposal: use a dedicated permitted sensor, keep images and temporary
tracks local and ephemeral, transmit minimized aggregates, restrict access and
set retention limits. Non-imaging sensors may be evaluated where suitable.
No permission to Lahore surveillance feeds or compliance with a vaguely cited
French agreement has been established. Privacy engineering does not remove the
need for actual local permissions and a deployment-specific review.

## 7. Pakistan-specific findings

PSCA's own ITMS description discusses traffic-data processing and signal
adjustment. Its signal-system procurement document includes installation,
commissioning and integration. A separate procurement specifies compatibility
with an urban traffic controller. These establish that local integration and
commissioning matter; they do not identify the cabinet at a future SABZ site,
provide an open API, or authorize camera access. Search-engine publication dates
for archived procurement files are unreliable; these are archival examples,
not confirmed active tenders.

Sources: [PSCA ITMS](https://psca.gop.pk/intelligent-traffic-management-system-itms/),
[signal-system procurement](https://psca.gop.pk/wp-content/uploads/2021/05/Traffic-Signal-Tender-Document.pdf),
[timer compatibility procurement](https://psca.gop.pk/wp-content/uploads/2021/03/PPRA-Upload-BD-Signal-Timers.pdf).

## 8. Honest SABZ gap assessment

| Area | Present in repository | Still needed |
|---|---|---|
| Adaptive control | Bounded two-phase bench scheduler, fairness, downstream supply | General movement/phase support and validated site behaviour |
| Perception | Experimental counting and metric input protocol | Implemented calibrated sensing and independently measured local accuracy |
| Signal operation | Timed kernel and process-level cabinet emulator | Real documented adapter, physical readback and independent safety equipment |
| Approach protection | Bounded synthetic tests | Validated sensor/trajectory and site-specific safety design |
| Failure handling | Bench fault clearance and latching | Site-defined fallback, mode handover and recovery reconciliation |
| Security | TLS, roles, replay checks, bounded requests | Device lifecycle, update/config integrity, host hardening and independent assessment |
| Deployment | Installation guide, preflight, Linux service template | Actual Linux/service verification, sensor deployment and physical commissioning |
| Evidence | 68 local source/installed-package tests; synthetic traces | Integrated hardware evidence, field metrics and acceptance records |
| Operations | Local audit, basic health/status | Retention, fleet management, maintenance procedures exercised on equipment |

## 9. Next engineering priorities

First: define supported movements and a physical controller interface contract,
including allowed requests, readback semantics, fallback and restart handover.
Second: implement calibrated local sensing with accuracy and latency measurement.
Third: implement the selected controller adapter and qualify it on isolated real
hardware. Fourth: execute integrated security, failure and performance acceptance.
Only then commission an authorised installation and measure whether the product
improves traffic against a credible baseline. Model training serves these
measurable needs; it is not itself the completion criterion.

A completed product is a supported installed system with demonstrated behaviour
and accepted limits. Another video, more test counts alone, or a trained model
cannot close the missing hardware, sensing and commissioning requirements.
