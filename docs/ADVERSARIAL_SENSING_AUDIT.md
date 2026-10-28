# Cyberattack and incorrect-perception audit

This audit tests a different claim from the honest-demand scenario matrix.
A packet can pass authentication, schema, sequence and freshness checks while
its physical assertions are false. No language model controls SABZ lamps; the
active scheduler is deterministic. Computer vision can still confidently miss,
misclassify or duplicate vehicles. Stolen credentials or a compromised sensor
can fabricate the same aggregate inputs without breaking TLS.

## Findings reproduced in an isolated virtual test

Command: `python -m examples.adversarial_sensor_audit`.
Evidence: `validation/dishonest-sensor-audit.json`.
No network, serial port, camera or physical output was accessed.

| Input condition | Observed result | Interpretation |
|---|---|---|
| Valid fresh reports of 500 NS vehicles and zero EW, with assumed real EW demand | EW receives no green during 180 s; NS green intervals remain bounded to 60 s | Maximum GREEN does not imply maximum RED. Hidden demand can be starved |
| Same lie plus a continuous forged approaching-vehicle stream | Green still capped at 60 s, but EW remains unserved | Bounded 70 m protection limits extension, not the truth of demand |
| Valid fresh `conflict_clear=true` while physical occupancy is assumed | Emulated green is released | A packet alone cannot prove a physically clear intersection |
| Forged all-full receiving-road state | All-red and no service | Denial of service cannot safely be solved by ignoring the asserted blockage |

The earlier 292 scenarios exercised the stated synthetic sensing conditions and
selected timing/service properties. They did not establish resistance to a
compromised authorized sensor. These findings are unresolved release blockers,
not successful adversary resistance. `security_qualified` remains false.

## Required independent boundaries

1. Perception/optimization proposes bounded decisions; it must not own arbitrary
   lamp writes or change clearance, conflict rules or protected firmware remotely.
2. A local qualified controller enforces the reviewed movement conflict matrix,
   timing, startup/restart and failure plans. Valid attacker requests can still
   harm availability even when conflicting greens are prohibited.
3. Physical electrical conflict protection measures actual outputs independently
   of the AI computer. It addresses conflicting indications/electrical faults;
   it does NOT establish that a junction is physically empty.
4. Independently validated occupancy/presence sensing is required for physical
   clearance and detection disagreement. An ESP32 switch/input is a bench gating
   mechanism, not a validated road occupancy sensor. Reusing the same camera/model,
   host, key or power source does not automatically provide independence.
5. An approved fallback can serve or recall movements using trusted local inputs
   when adaptive sensing is unreliable. A maximum-red/service-opportunity policy
   needs that movement/fallback design. Blindly forcing a green can release into
   a blocked/occupied junction; indefinite all-red is not a universal road plan.
6. Local operator control, alarms and recovery procedures must remain available
   when central communication, sensor quality or optimization is lost.

The compiled C++ core already gates startup green on its local clearance input,
checks phase sequencing and expires command leases. Electrical behaviour is
unverified; firmware takeover, power loss or wiring faults are not defeated by
those software rules. Secure boot, production signing/key provisioning,
authenticated serial transport and independent physical monitoring are open.
CRC is not authentication. A source hash pins bytes; it does not establish that
a model is accurate or trustworthy.

## How to treat uncertain or adversarial perception

- Do not treat high model confidence as proof. Validate false-negative/false-positive
  behaviour separately for motorcycles, darkness, weather, crowding and occlusion.
- Withdraw health on expired/invalid measurements; the strict bench path already
  inhibits new greens and requests yellow/clearance. This is a tested bench
  behaviour, not the final site-approved operating fallback.
- Compare genuinely independent evidence and detect implausible counts, stuck
  frames, missing tracks and disagreement. Present health checks are incomplete;
  an empty detection output is not proof of an empty road.
- Under disagreement or a security incident, invoke the local reviewed fallback
  and alert operators. No language model should invent that response.
- Test plausible lies, compromised credentials/hosts, corrupted updates, clock
  faults, floods, sensor obstruction, restart and power faults in controlled rigs.
  Define requirements and evidence per hazard; no finite test set proves that all
  possible attacks or all perception errors are covered.

## Network/device protection still required

Separate sensor, control and management networks; unique device identities and
least privilege; restricted management access; protected configuration/updates;
reviewed key provisioning/rotation/revocation; audit protection; patch and
recovery management; monitoring and controlled remote access. These are planned
production requirements, not completed capabilities implied by the existing TLS
endpoint. Host compromise can bypass two processes running under the same account.
Independent hardware and power boundaries must be evaluated separately.

[NIST SP 800-82 Rev.3](https://csrc.nist.gov/pubs/sp/800/82/r3/final) addresses OT
security together with reliability, performance and safety. It is guidance, not
SABZ certification. [FHWA failure scenarios](https://ops.fhwa.dot.gov/publications/fhwahop11027/ap_c.htm)
describe detector substitution/recall, alarms and user-specified local/time-of-day
fallback, supporting the need for an engineered operating plan rather than an
unconditional software response. Neither source grants Pakistani road approval.

Only the isolated low-voltage bench is appropriate for the next hardware tests.
Road output remains disabled until the corresponding hazards are addressed and
independent hardware/site acceptance is complete.
