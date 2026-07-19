# Approved facts and sanitization rules

**Hard constraint.** Every document in `data/raw/` must be writable from *generic* freight-exchange
and logistics-engineering knowledge **plus only the figures in the allowlist below**. Nothing else
about any real employer enters the knowledge base.

## Allowlist — the only real-world figures permitted

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
| 12 | (employer and city redacted) | **none — planning docs only** |

Document numbers refer to [`04-corpus-plan.md`](04-corpus-plan.md) and
[`assets/document-set.json`](assets/document-set.json) (`approved_figures` per document).

**On #12:** the company is never named in the knowledge base. The submission README deliberately
writes around it ("a live digital logistics platform serving 8,500+ logistics service providers
across Europe") — see [`templates/README-submission.md`](templates/README-submission.md).

## Forbidden — no exceptions

- Internal service names, schemas, table names, code, or internal processes
- Any personally identifiable information
- Employment tenure dates **inside the knowledge base documents** (planning documents may
  reference them; `data/raw/` may not)
- Any figure not in the allowlist above, however innocuous it seems

## Authoring voice rule

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

## Pre-submission grep pass

Before submitting, sweep `data/raw/` for leaked specifics. Extend the pattern list with any
internal term you know you must avoid:

```bash
# 1. Numbers that are NOT on the allowlist
grep -rnoE '[0-9][0-9,.]*\+?\s*(req|rps|ms|s\b|k\b|m\b|%|vehicles|services|LSPs|customers|users)' data/raw/ \
  | sort -u

# 2. Company / product / internal identifiers (extend this list yourself)
grep -rniE 'teg|transport exchange|courier ?exchange|haulage ?exchange' data/raw/

# 3. Declarative first-person voice — every hit needs rewording per the table above
grep -rniE '\b(we|our|us) (use|used|run|ran|have|had|built|deploy|store)\b' data/raw/

# 4. Dates that could be tenure
grep -rnoE '\b(19|20)[0-9]{2}\b' data/raw/
```

Every hit in #1 must match a row in the allowlist. Every hit in #2 must be zero. Hits in #3 and #4
must be rewritten or removed.

The knowledge base contains no personal data by construction — tenure dates are intentionally
unused.
