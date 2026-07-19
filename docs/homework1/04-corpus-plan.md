# Corpus plan — the seven source documents

**This is the actual work.** Nothing else in this folder can run until at least three of these
exist in `data/raw/`. None are written yet.

Seven documents are designed, inside the spec's 3–10 band. They are split into a **core four** —
author these first, they alone give full rubric coverage with one document per `document_type` —
and an **extension three**, added when time allows. The pipeline is deterministic and
re-runnable, so extending the corpus later is a one-command re-chunk.

Machine-readable version: [`assets/document-set.json`](assets/document-set.json) — use it to
generate `data/raw/` stubs and to fill the submission README's Sources table.

## Status

| # | File | Type | Tier | Target words | Est. chunks | Status |
|---|---|---|---|---|---|---|
| 1 | `freight-exchange-domain-primer.md` | concept-guide | core | 1,300–1,600 | 13–16 | ❌ not written |
| 2 | `cqrs-event-sourcing-for-logistics.md` | architecture-guide | core | 1,500–1,900 | 15–19 | ❌ not written |
| 3 | `monolith-to-microservices-migration.md` | case-study | core | 1,500–2,000 | 15–20 | ❌ not written |
| 4 | `scaling-and-zero-downtime-operations.md` | playbook | core | 1,300–1,700 | 13–17 | ❌ not written |
| 5 | `real-time-freight-visibility.md` | concept-guide | extension | 1,200–1,500 | 12–15 | ❌ not written |
| 6 | `kafka-vehicle-telemetry-streaming.md` | architecture-guide | extension | 1,400–1,800 | 14–18 | ❌ not written |
| 7 | `freight-payments-automation.md` | concept-guide | extension | 1,100–1,400 | 11–14 | ❌ not written |
| | **Core four** | | | **5,600–7,200** | **56–72** | |
| | **All seven** | | | **9,300–11,900** | **93–119** | |

**Sizing rule:** at chunk_size 800 / overlap 150 the net yield is ~650 chars per chunk, and
English technical prose runs ~6.5 chars per word — so **chunks ≈ words ÷ 10**. (The original
blueprint quoted 55–75 and 86–119; those did not follow its own rule and did not sum. Corrected
above.)

**Shared metadata for every document:** `language: en`, `domain: logistics-engineering`,
`source_type: markdown`. Only `document_type` varies.

**Section metadata** comes from each document's H2/H3 headings — the outlines below define them.
The H1 is the document title; any body before the first H2 becomes an `"Introduction"` section.
So `metadata.section` is never the title. Full rule: [`05-chunking-strategy.md`](05-chunking-strategy.md).

**Before writing a word**, read [`02-approved-facts.md`](02-approved-facts.md). Every document
lists the approved figures it may use; nothing else about a real platform may appear.

---

## Core four

### 1. `freight-exchange-domain-primer.md`
**"Freight Exchange Fundamentals: Actors, Loads, and Matching"** · concept-guide · ~1,300–1,600 words

- **What a freight exchange is** — two-sided marketplace; contrast with brokerage and private fleets
- **Core actors and roles** — shipper, carrier, freight forwarder, LSP; scale note: 8,500+ LSPs across Europe
- **The load lifecycle** — posted → matched → booked → in transit → delivered → settled; who triggers each transition
- **Load matching mechanics** — search filters (lane, vehicle type, weight, dates), ranking, backhaul optimization
- **Trust and vetting** — carrier verification, insurance checks, ratings
- **Key domain vocabulary** — lane, spot vs contract freight, FTL/LTL, tender, POD

*Writability:* entirely generic freight-marketplace knowledge.
*Approved figures:* 8,500+ LSPs across Europe · 5,000 req/s.

### 2. `cqrs-event-sourcing-for-logistics.md`
**"CQRS and Event Sourcing in a Freight Platform"** · architecture-guide · ~1,500–1,900 words

- **Why CQRS fits freight** — read/write asymmetry: few bookings, massive search and tracking reads
- **Command side** — load/booking aggregates, invariants, validation before events are emitted
- **Event sourcing basics** — event store as source of truth, replay, immutability
- **Designing logistics events** — `LoadPosted`, `LoadBooked`, `PositionUpdated`; naming, granularity, versioning
- **Projections and read models** — denormalized search indexes; eventual consistency and UX
- **Operational realities** — snapshotting, replay cost, schema evolution; when *not* to event-source (a platform of ~40 microservices applies CQRS + ES selectively, not everywhere)

*Writability:* standard CQRS/ES literature applied to generic freight entities.
*Approved figures:* CQRS + Event Sourcing · ~40 microservices · automated payment solutions.

### 3. `monolith-to-microservices-migration.md`
**"Migrating a Logistics Monolith to Microservices"** · case-study · ~1,500–2,000 words

> **Framing note — put this in the document's introduction:** the narrative is a generic composite
> of standard strangler-fig practice, anchored only by the approved end-state figures (~40
> services, zero-downtime sync, monolith decommissioned). Mirror this in the submission README's
> no-proprietary note.

- **Starting point** — why logistics monoliths hit the wall: coupled deploys, hot search/tracking vs cold CRUD
- **Carving service boundaries** — bounded contexts along the load lifecycle: matching, tracking, payments, identity
- **Strangler-fig execution** — routing layer, extracting one capability at a time, anti-corruption layers
- **Keeping data in sync mid-migration** — Kafka event-driven sync between old and new owners; zero-downtime sync
- **Cutover and decommissioning** — traffic shadowing, verification, actually deleting the monolith (end state: ~40 services)
- **Lessons learned** — what to extract first, migration fatigue, when to stop splitting

*Writability:* generic strangler-fig / DDD playbook.
*Approved figures:* completed migration · ~40 services · zero-downtime sync · Kafka.

### 4. `scaling-and-zero-downtime-operations.md`
**"Operating a Freight Platform at 5,000 Requests per Second"** · playbook · ~1,300–1,700 words

- **The load profile** — spiky search traffic, steady telemetry firehose, business-hours booking peaks
- **Horizontal scaling patterns** — stateless services, autoscaling signals; the datastore is the limit, not the app tier
- **Caching strategy** — search results, reference data, position snapshots; invalidation via events
- **Zero-downtime deployments** — rolling / blue-green, backward-compatible changes, expand-contract migrations
- **Resilience** — timeouts, retry budgets, circuit breakers that fail visibly; bulkheading tracking from booking
- **Observability** — golden signals, consumer-lag and telemetry-freshness SLOs, alerting on staleness

*Writability:* standard SRE practice.
*Approved figures:* 5,000 req/s · zero-downtime · ~40 microservices.

---

## Extension three

Author later. These unlock queries on visibility, telemetry, and payments.

### 5. `real-time-freight-visibility.md`
**"Real-Time Freight Visibility: From GPS Ping to Customer ETA"** · concept-guide · ~1,200–1,500 words

- **Why visibility matters** — detention costs, ETA-driven planning, customer trust
- **Telemetry sources** — telematics units, driver apps, GPS aggregators; typical ping frequencies
- **The ingestion path** — device → gateway → stream → position store; sub-5-second budget across 10,000+ vehicles
- **Position processing** — deduplication, map matching, geofencing, stop detection
- **ETA computation** — routing engines, historical lane times, delay signals
- **Data-quality pitfalls** — signal gaps, out-of-order pings, stale positions and visible degradation

*Writability:* generic telematics engineering.
*Approved figures:* sub-5-second telemetry · 10,000+ vehicles.

### 6. `kafka-vehicle-telemetry-streaming.md`
**"Streaming Vehicle Telemetry with Kafka"** · architecture-guide · ~1,400–1,800 words

- **Why a log-based broker** — decoupling, replay, backpressure vs queues
- **Topic and partition design** — keying by vehicle ID for per-vehicle ordering; sizing for 10,000+ vehicles
- **Producer path** — batching, compression, acks trade-offs against a sub-5-second end-to-end budget
- **Consumer patterns** — tracking consumers, data-sync consumers between services, consumer groups
- **Delivery semantics** — at-least-once default, idempotent position handling, exactly-once cost/benefit
- **Failure handling** — lag monitoring, dead-letter topics, replaying history for a rebuilt projection

*Writability:* public Kafka design knowledge.
*Approved figures:* Kafka for vehicle-tracking / data-sync · sub-5s · 10,000+ vehicles.

### 7. `freight-payments-automation.md`
**"Automating Freight Payments and Settlement"** · concept-guide · ~1,100–1,400 words

- **The manual baseline** — invoice-and-chase: PODs, 30–60 day terms, disputes
- **Automated settlement flow** — delivery confirmation → invoice → approval rules → payout; event-triggered
- **Trust features** — payment guarantees, early-payment options; retention lever for a marketplace of 8,500+ LSPs
- **Engineering concerns** — idempotent payment commands, ledger consistency, reconciliation
- **Compliance surface** — VAT across European jurisdictions, audit trails, KYC (concept level)
- **Failure modes** — duplicate invoices, disputed deliveries, failed payouts; visible-error handling

*Writability:* generic fintech / settlement knowledge at concept level.
*Approved figures:* automated payment solutions · 8,500+ LSPs.

---

## Authoring guidance

- **Prefer prose over lists and tables.** Vocabulary and checklist sections chunk badly and embed
  worse. Write "A lane is a recurring origin–destination corridor…" rather than a bullet.
- **No single table over ~800 characters.** Oversized tables split at row boundaries with no
  header repetition — see the table edge case in [`05-chunking-strategy.md`](05-chunking-strategy.md).
- **Aim sections at 800–1,600 characters.** Sections under 500 chars get merged; sections just
  over 800 leave an awkward tail. See [`09-open-defects.md`](09-open-defects.md) D1.
- **Use the outline headings as the actual H2s** — they become `metadata.section` verbatim.
