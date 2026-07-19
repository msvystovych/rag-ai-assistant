# Glossary

Domain and architecture vocabulary for the knowledge base. Pipeline terms (chunk size, overlap)
live in [`05-chunking-strategy.md`](05-chunking-strategy.md), which owns those definitions.

## Freight domain

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

## Architecture patterns

| Term | Meaning |
|---|---|
| **CQRS** | Command Query Responsibility Segregation — separate write model (commands) from read models (queries / projections). |
| **Event Sourcing** | Persisting every state change as an immutable event; current state is derived by replay. |
| **Projection / read model** | A denormalized view rebuilt from the event stream, optimized for queries. |
| **Strangler-fig migration** | Incrementally extracting capabilities from a monolith behind a routing facade until the monolith can be decommissioned. |
| **Anti-corruption layer** | A translation boundary preventing a legacy model from leaking into a new service's domain. |
| **Bounded context** | A boundary within which a domain model and its terms are internally consistent. |

## RAG terms

| Term | Meaning |
|---|---|
| **Chunk** | A self-contained slice of a document — the retrieval unit of a RAG system. Size rules: [`05-chunking-strategy.md`](05-chunking-strategy.md). |
| **Metadata** | Per-chunk fields (`document_id`, `section`, `domain`, …) enabling filtered retrieval and citation. Contract: [`06-chunk-schema.md`](06-chunk-schema.md). |
| **JSONL** | One JSON object per line — the required format of `data/processed/chunks.jsonl`. |
| **Breadcrumb prefix** | The `"<Doc Title> > <Section>. "` string prepended to every chunk's text so it reads standalone. |
