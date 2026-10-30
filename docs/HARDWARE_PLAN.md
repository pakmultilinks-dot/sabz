# SABZ hardware plan and cost estimate (Pakistan)

Status: planning document, 2026-10-30. Prices are market ranges from local
listings and typical Pakistani retail as of the research date — **not quotes**.
Every line must be re-quoted before purchase. Nothing has been ordered.

Related: [HARDWARE.md](HARDWARE.md) (decision + safety constraints),
[BENCH_SHOPPING_AND_ASSEMBLY.md](BENCH_SHOPPING_AND_ASSEMBLY.md) (exact bench
parts and assembly), [PHYSICAL_BENCH.md](PHYSICAL_BENCH.md) (firmware/protocol).

## Stage 0 — Desk demonstrator (no road, no mains)

Purpose: prove physical I/O end-to-end — edge software → serial → ESP32
firmware → LEDs, with watchdog, readback and cable-pull tests. This is the
"we built a real controller" evidence for judges and buyers.

| Item | Est. PKR | Notes |
|---|---|---|
| ESP32-S3-DevKitC-1 (N8R8, headers soldered) | 1,500 – 9,800 | Daraz listing showed Rs 9,783; out-of-stock listing showed Rs 1,500. Verify authenticity with PCB photos |
| 6 LEDs (R/A/G, 5 mm diffused) + resistors + breadboard + jumpers | 500 – 1,000 | Breadboard listed at Rs 300 |
| 2 momentary SPDT switches + USB data cable + multimeter (borrow) | 500 – 1,500 | Confirm COM/NC/NO with seller |
| Insulated base, labels, heat-shrink | 200 – 500 | |
| **Stage 0 total** | **~3,000 – 13,000** | Buy after board variant confirmed |

Firmware and native tests already exist; flashing and electrical checks are
the remaining work. One person can assemble this in an afternoon.

## Stage 1 — Single-junction pilot (real road, with authority)

Purpose: one live junction in shadow mode first (SABZ observes, cabinet keeps
control), then bounded advisory control. **Gate: authority approval is a hard
prerequisite** — see HARDWARE.md; do not buy field hardware before the
junction, cabinet model and integration protocol are confirmed.

| Item | Est. PKR | Notes |
|---|---|---|
| Edge appliance (mini PC / industrial fanless box, i5-class, 16 GB RAM, 256 GB SSD) | 60,000 – 150,000 | Reuse an existing laptop first; spec finalized after vision latency is measured on real footage |
| Camera (2–4 MP IP, IR, PoE, IP67) + PoE switch + cabling | 25,000 – 80,000 | Authority may already own cameras — check first |
| Camera pole/bracket installation + electrician | 15,000 – 50,000 | Site-dependent |
| UPS (1 kVA online) for edge + camera | 25,000 – 60,000 | Cabinet power is the authority's scope |
| Cabinet integration work (protocol adapter, isolation, readback wiring) | 50,000 – 200,000 | Highly variable; depends on cabinet make/model. NTCIP-capable cabinets are cheaper to integrate |
| Enclosure, surge protection, misc. | 10,000 – 30,000 | |
| Commissioning + 1 month monitoring labour | 50,000 – 150,000 | Your team's time or partner |
| **Stage 1 total (hardware only)** | **~185,000 – 570,000** | Excluding authority fees and camera reuse |

## Stage 2 — Corridor scale (5–10 junctions)

Marginal cost per additional junction drops because coordination software is
already shipped and the edge appliance can serve 2–3 junctions:

| Item | Est. PKR per junction |
|---|---|
| Additional cameras + cabling (if not pre-existing) | 25,000 – 80,000 |
| Edge appliance share (1 box per 2–3 junctions) | 25,000 – 75,000 |
| Cabinet integration (same model = repeatable) | 30,000 – 100,000 |
| **Marginal total per junction** | **~80,000 – 255,000** |

## What the money buys vs competitors

- InLights sells a platform (traffic + lighting + ANPR) — capital-heavy,
  central. SABZ is edge-first: no cloud bill, no per-junction licence server.
- SCOOT/SCATS retrofits require a regional master plan and vendor contracts.
  SABZ coordination is decentralized — junctions join one at a time.
- The safety kernel and 368-test suite ship free with every unit; the
  competitor's equivalent is closed vendor firmware.

## Honest caveats (say these out loud to any buyer)

1. All prices are listing-based ranges, re-quote before any purchase.
2. Cabinet integration is the biggest cost uncertainty — it collapses once
   the authority names the cabinet make/model.
3. Vision accuracy on Lahore traffic is **pending phone-footage validation**;
   the edge appliance spec is deliberately not finalized until that lands.
4. No road hardware purchase before: junction selected, authority approval,
   cabinet protocol documented, movement/phase plan approved.

## Recommended order of operations

1. ✅ Software complete (done — 368 tests, benchmarks, security review).
2. 📱 Phone vision validation (in progress — awaiting footage).
3. 🔧 Stage 0 desk demonstrator (~PKR 3k–13k, one afternoon).
4. 🤝 Authority conversation with Stage 1 plan in hand.
5. 🛒 Stage 1 procurement after gates clear.