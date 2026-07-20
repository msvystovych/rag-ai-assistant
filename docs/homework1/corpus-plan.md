# Corpus plan — the seven source documents

**This is the actual work.** Nothing downstream can run until at least three of these exist in
`data/raw/`. None are written yet.

Seven documents are designed, inside the spec's 3–10 band, split into a **core four** — author
these first, they alone give full rubric coverage with one document per `document_type` — and an
**extension three**, added when time allows. The pipeline is deterministic and re-runnable, so
extending the corpus later is a one-command re-chunk.

**Read § Sanitization below before writing a word.** Every document lists the approved figures it
may use; nothing else about a real platform may appear.

---

## Sanitization — the hard constraint

Every document in `data/raw/` must be writable from *generic* freight-exchange and
logistics-engineering knowledge **plus only the figures in the allowlist below**. Nothing else
about any real employer enters the knowledge base.

### Allowlist — the only real-world figures permitted

| # | Approved figure | Documents it belongs in |
|---|---|---|
| 1 | 5,000 requests per second | 1, 4 |
| 2 | 8,500+ logistics service providers across Europe | 1, 7 |
| 3 | 10,000+ vehicles tracked | 5, 6 |
| 4 | Sub-5-second telemetry | 5, 6 |
| 5 | ~40 microservices | 2, 3, 4 |
| 6 | Completed monolith-to-microservices migration, monolith fully decommissioned | 3 |
| 7 | Zero-downtime sync | 3, 4 |
| 8 | CQRS + Event Sourcing | 2 |
| 9 | Kafka event streaming for vehicle tracking / data sync | 3, 6 |
| 10 | Automated payment solutions | 2, 7 |
| 11 | Real-time freight visibility | 5 |
| 12 | *(employer name and city — redacted)* | **none — never written anywhere in this repository** |

**On #12:** the company is never named, in the knowledge base or in these planning notes. The
submission README deliberately writes around it ("a live digital logistics platform serving 8,500+
logistics service providers across Europe").

### Forbidden — no exceptions

- Internal service names, schemas, table names, code, or internal processes
- Any personally identifiable information
- Employment tenure dates — **anywhere in this repository**, not just in `data/raw/`. The earlier
  rule carved out planning documents; that carve-out is withdrawn, because the planning documents
  ship with the submission too.
- Any figure not in the allowlist above, however innocuous it seems

### Authoring voice rule

The approved figures set the **scale context**. Implementation specifics stay in generic or
normative voice — never as declarative facts about a real platform's internals.

| ✅ Write this | ❌ Never this |
|---|---|
| "At 5,000 requests per second, matching must be index-backed rather than scan-based." | "Our matching service uses an index because we do 5,000 req/s." |
| "A common design is to partition the position stream by vehicle identifier." | "We partition the position topic by vehicle ID." |
| "At this scale, X must be Y." | "X is Y in production." |

Useful phrasings: *is typically* · *a common design is* · *at this scale, X must* · *commonly* ·
*is usually*.

The migration case study (document 3) is **explicitly a generic composite** of standard
strangler-fig practice, anchored only by the approved end-state figures. Say so in its
introduction, and mirror the note in the submission README.

### Grep pass — sweep 1 of 2, run this one while authoring

Scoped to `data/raw/` and run **before chunking** — fixing prose after a run means re-running.
The second sweep (whole-repo, run last) is in [`README.md`](README.md) § Pre-submission gate; these
two are deliberately different checks, not a drifted duplicate.

```bash
# 1. Numbers that are NOT on the allowlist
grep -rnoE '[0-9][0-9,.]*\+?\s*(req|rps|ms|s\b|k\b|m\b|%|vehicles|services|LSPs|customers|users)' data/raw/ \
  | sort -u

# 2. Company / product / internal identifiers.
#    Fill BRAND_PATTERN in locally; do not commit the real tokens to this repo.
grep -rniE "${BRAND_PATTERN:?set BRAND_PATTERN to your employer/product name alternation}" data/raw/

# 3. Declarative first-person voice — every hit needs rewording per the table above
grep -rniE '\b(we|our|us) (use|used|run|ran|have|had|built|deploy|store)\b' data/raw/

# 4. Dates that could be tenure
grep -rnoE '\b(19|20)[0-9]{2}\b' data/raw/
```

Every hit in #1 must match a row in the allowlist. Every hit in #2 must be zero. Hits in #3 and #4
must be rewritten or removed.

The knowledge base contains no personal data by construction — tenure dates are intentionally
unused.

---

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

**Sizing rule:** at chunk_size 800 / overlap 150 the net yield is ~650 chars per chunk, and English
technical prose runs ~6.5 chars per word — so **chunks ≈ words ÷ 10**.

**Minimum viable corpus:** `spec:25` requires three documents and `spec:72` awards its 5 points for
"Файли присутні, читаються" — no rubric row mentions length. Three documents at ~900 words each
still clears the spec, still yields ~27 chunks, and still exercises the full pipeline. It costs one
`document_type` enum value. Prefer the core four; fall back to three rather than shipping nothing.

**Every document opens with YAML front-matter** carrying its `document_type` (decision 10). The
splitter strips it during normalization:

```markdown
---
document_type: concept-guide
---

# Freight Exchange Fundamentals: Actors, Loads, and Matching
```

**Shared metadata for every document:** `language: en`, `domain: logistics-engineering`,
`source_type: markdown`. Only `document_type` varies.

**Section metadata** comes from each document's H2/H3 headings — the outlines below define them.
The H1 is the document title; any body before the first H2 becomes an `"Introduction"` section.
So `metadata.section` is never the title. Full rule: [`pipeline-spec.md`](pipeline-spec.md).

## Authoring guidance

Read this before writing the first document — it shapes how the outlines below should be written.

- **Prefer prose over lists and tables.** Vocabulary and checklist sections chunk badly and embed
  worse. Write "A lane is a recurring origin–destination corridor…" rather than a bullet.
- **No single table over ~800 characters.** Oversized tables split at row boundaries with no header
  repetition — see the table edge case in [`pipeline-spec.md`](pipeline-spec.md).
- **Aim sections at 800–1,600 characters.** Sections under 500 chars get merged; sections just over
  800 leave an awkward tail.
- **Use the outline headings as the actual H2s** — they become `metadata.section` verbatim, so pick
  one casing convention and hold it across every document.

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
*Approved figures:* sub-5-second telemetry · 10,000+ vehicles · real-time freight visibility.

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

## Domain vocabulary

The terms the corpus should define and use consistently. Homework #2 draws its test queries from
this vocabulary.

### Freight domain

| Term | Meaning |
|---|---|
| **Freight exchange** | Two-sided marketplace matching shippers' loads with carriers' vehicle capacity. |
| **Load** | A shipment posted for transport. Lifecycle: posted → matched → booked → in transit → delivered → settled. |
| **Shipper** | The party sending the freight. |
| **Carrier** | The party moving the freight. |
| **LSP** | Logistics service provider — a participant offering logistics services on the platform. |
| **Freight forwarder** | An intermediary arranging transport on a shipper's behalf. |
| **POD** | Proof of delivery — the confirmation document that triggers settlement. |
| **Freight visibility** | Real-time knowledge of where a shipment is and when it will arrive (ETA). |
| **Lane** | A recurring origin–destination corridor. |
| **Spot vs contract freight** | One-off market-priced shipments vs pre-agreed rates over a period. |
| **FTL / LTL** | Full truckload vs less-than-truckload. |
| **Tender** | An offer of a load to a specific carrier at agreed terms. |
| **Backhaul** | A return-leg load that avoids running a vehicle empty. |

### Architecture patterns

| Term | Meaning |
|---|---|
| **CQRS** | Command Query Responsibility Segregation — separate write model (commands) from read models (queries / projections). |
| **Event Sourcing** | Persisting every state change as an immutable event; current state is derived by replay. |
| **Projection / read model** | A denormalized view rebuilt from the event stream, optimized for queries. |
| **Strangler-fig migration** | Incrementally extracting capabilities from a monolith behind a routing facade until the monolith can be decommissioned. |
| **Anti-corruption layer** | A translation boundary preventing a legacy model from leaking into a new service's domain. |
| **Bounded context** | A boundary within which a domain model and its terms are internally consistent. |
