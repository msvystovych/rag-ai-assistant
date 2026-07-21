---
document_type: case-study
---

# Migrating a Logistics Monolith to Microservices

## Introduction

This narrative is a generic composite of standard strangler-fig practice as it is applied to freight and logistics platforms. It is not a report on any specific company, team, or system. Every step described here is drawn from published migration literature and from patterns that recur across the industry; the only concrete anchors are the end-state figures of a completed migration — a landscape of roughly forty microservices, event-driven data synchronisation performed with zero downtime, and a legacy monolith that was ultimately switched off and deleted rather than left running as a dormant fallback. Everything between the starting point and that end state is written in normative voice: what a migration of this shape typically requires, why the pattern exists, and what it costs.

The document walks the migration in the order it is usually executed. It begins with the pressures that push a logistics monolith past its useful life, then covers how bounded contexts are carved along the load lifecycle, how capabilities are extracted one at a time behind a routing facade, how data is kept consistent between the old and new owners while both are live, and how the cutover and the final decommissioning are verified. It closes with the judgement calls that decide whether such a programme finishes or stalls.

## Starting Point: Why Logistics Monoliths Hit The Wall

A freight platform usually starts as a single deployable that owns load posting, search, booking, tracking, invoicing, and user administration in one codebase and one database schema. That design is correct at the beginning: transactional consistency is free, a join answers most questions, and one pipeline serves the whole product. The wall it eventually hits is rarely raw compute. It is coupling.

The first symptom is coupled deploys. When invoicing, matching, and telemetry ingestion ship as one artifact, the release cadence of the entire platform collapses to that of its most fragile component. A settlement-rule change cannot go out while a tracking refactor is mid-flight, so releases are batched, batches grow, and each batch carries more risk than the last — which encourages even larger batches.

The second symptom is a workload profile the monolith cannot express. Logistics traffic is strongly asymmetric: search and tracking are hot, read-dominated, latency-sensitive paths, while contract administration and tariff maintenance are cold CRUD paths invoked rarely. A monolith scales as a unit, so serving the hot paths means replicating the cold ones alongside them.

The third symptom is shared-database contention. A single schema means a telemetry write path and an invoice report compete for the same buffer cache, locks, and replication-lag budget, and nothing in the codebase makes that dependency visible. At that point the database, not the application tier, is the binding constraint, and replicating the monolith does not relieve it.

## Carving Service Boundaries

Boundaries are the whole migration; everything else is mechanics. The reliable technique is to derive them from bounded contexts in the domain rather than from the existing package structure, because the package structure encodes the coupling that is being escaped. In freight, the load lifecycle supplies a natural set of seams: a load is posted and matched, a booking is agreed, the vehicle is tracked in transit, delivery is confirmed, and settlement follows. Each stage has its own vocabulary, consistency requirements, and change cadence.

Matching is typically the clearest context. It owns load offers, search, ranking, and capacity discovery; its data is short-lived and read-dominated, and its correctness criterion is relevance rather than transactional integrity. Tracking is equally distinct, owning positions, ETAs, and geofence events under a continuous ingest stream with little in common with request-response CRUD. Payments and settlement form a third context whose defining property is the opposite: strict auditability, idempotency, and an immutable ledger. Identity and access sits underneath all of them as a platform capability rather than a lifecycle stage.

Choosing where to place a seam is largely a test of what crosses it. A good seam carries few, stable, coarse-grained messages — a booking confirmation, a delivery confirmation — and no chatty per-request lookups. A poor seam is one where both sides must agree on a shared invariant transactionally, because that agreement becomes a distributed transaction the moment the seam is cut. The trade-off is that domain-derived seams rarely align with existing tables, so early extractions carry a data-remodelling cost that a package-derived split appears to avoid and then pays back with interest.

## Strangler-Fig Execution

The strangler-fig pattern replaces a system incrementally by intercepting calls at its edge and redirecting them, capability by capability, until nothing routes to the original. It is preferred over a rewrite because it keeps the product shippable throughout, and because each increment is independently reversible.

The first structural move is a routing facade in front of the monolith — usually an API gateway or reverse proxy that owns the public contract and can route any route, method, or traffic slice to either the legacy implementation or a new service. It must exist before the first extraction, because it is what makes every later step incremental and every rollback a routing change rather than a redeploy. Clients are pointed at the facade while it still forwards everything to the monolith, so the topology change and the behaviour changes are never in flight together.

Extraction then proceeds one capability at a time, and a capability is lifted with its data rather than only its logic: a service that owns behaviour but still reads the monolith's tables is a distributed monolith with worse latency and no independence.

Between the two models sits an anti-corruption layer, a translation boundary mapping legacy representations into the new service's domain language and back. Its purpose is to stop the legacy schema's accidental structure — nullable columns, encoded status flags — becoming permanent vocabulary in the new context. It is deliberately throwaway code with a defined end of life at cutover; treating it as durable is a common way to preserve the very model the migration was meant to retire.

## Keeping Data In Sync Mid-Migration

For most of a migration both the monolith and a new service hold data for the same context, and both must be correct. Batch replication is unsuitable: it is either too infrequent to serve live reads or too aggressive to run against an operational database. Event-driven synchronisation over a durable log such as Kafka is the standard answer, because a log-based broker gives ordered, replayable, at-least-once delivery and lets the two sides progress at different speeds without either blocking the other.

The usual arrangement is that whichever side currently owns a piece of data publishes change events and the other consumes them into its own store. While the monolith is authoritative, an outbox or change-data-capture feed turns its committed writes into events; once ownership transfers, the new service publishes and the monolith consumes, so the same channel serves the reverse direction. Consumers must be idempotent, since at-least-once delivery eventually produces duplicates, and events are commonly keyed by entity identifier so per-entity ordering is preserved within a partition.

Zero-downtime sync is achieved by never making a switch that requires both sides to change at once: replication first, then a period in which both stores are live and only one is read, then a read switch, then retirement of the old writer — expand, migrate, contract, each step independently deployable and reversible.

Record-level parity verification is what makes the read switch safe. A continuous comparison job reads the same entities from both stores and reports field-level differences, and the switch waits until the mismatch stream stays empty across a full business cycle. Aggregate row counts are insufficient: they hide compensating errors and say nothing about drift in a single field.

## Cutover And Decommissioning

Cutover is the least dramatic part of a well-run migration, because most of the risk has already been retired. Traffic shadowing is the usual final rehearsal: production requests are duplicated to the new service while the monolith's responses remain authoritative, and the two are compared offline. Shadowing exercises the new path with real traffic shapes — odd payloads, legacy clients, concurrency patterns no synthetic test generates — while a divergence costs nothing but a log line. Write paths need care, since a shadowed write must be idempotent or diverted to an isolated store, and side effects such as notifications and payouts must be suppressed on the shadow path.

Live traffic then moves gradually through the routing facade, typically starting with a small slice, then a defined tenant or region, then the remainder, with error rate, latency distribution, and business-level counters watched at each step. Because the facade owns the routing decision, rollback is a configuration change rather than a deployment, which is what makes an aggressive ramp defensible.

Decommissioning is the step most programmes skip, and skipping it forfeits most of the benefit. Once no route resolves to a legacy capability, its code, tables, scheduled jobs, and dashboards are deleted. A monolith left running "just in case" keeps consuming infrastructure, keeps appearing in vulnerability reports, and keeps tempting engineers into fixing bugs in the retired implementation. A migration counts as complete only when the monolith is fully decommissioned — the end state here being roughly forty microservices, each mapping to a bounded context or platform capability.

## Lessons Learned

The most consequential decision is what to extract first. The instinct is to start with the most painful component, but the more effective choice is usually a capability that is genuinely peripheral, has a clean seam, and delivers a visible benefit — often a read-heavy path such as search or tracking, which can be extracted with a replica rather than a full ownership transfer. The first extraction's real product is the migration machinery itself: the routing facade, the event backbone, the parity verifier, the deployment and observability templates. Paying for that machinery on a low-risk capability, and only then attacking the hard core, is what separates programmes that finish from those abandoned halfway.

Migration fatigue is a scheduling problem rather than a motivation problem. A multi-year extraction competing with feature work will lose unless each increment ships user-visible or operator-visible value, so migration work is best framed as the enabling half of a feature rather than a separate refactoring track. Long-lived anti-corruption layers and permanent dual-write paths are the visible symptoms; when temporary scaffolding starts appearing in architecture diagrams as though it were permanent, the programme has stalled.

The third lesson is knowing when to stop. Service count is a cost, not an achievement: every additional service adds a pipeline, a schema to evolve, an on-call surface, and a network hop where a method call used to be. Splitting should continue only while a boundary buys independent deployability, scaling, or failure — and stop where a proposed split would require the two halves to release together. Teams that keep splitting past that point rebuild the monolith's coupling over the network, where it is materially harder to debug.
