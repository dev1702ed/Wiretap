# Roadmap

Three-week v1 sprint. Critical path is **P0 → P1 → P2 → P5**. P3 and P4 make DCP
*usable*; P2 and P5 make it *true*. If the clock slips, P3/P4 compress — never P5.

| Phase | Goal | Deliverable | Days | Status |
|---|---|---|---|---|
| **P0** | Lock the spec | `spec/` envelope + identity scheme + JSON Schema in CI; adversarial suite written as failing tests | 1–2 | ☐ |
| **P1** | Capture one protocol | `dcp.patch_psycopg()` emits schema-valid dataset events | 3–4 | ☐ |
| **P2** | Prove multi-hop | Kafka interceptor + contextvars + header propagation; 2-hop flow links | 4–5 | ☐ |
| **P3** | Queryable lineage | FastAPI ingest → networkx → `GET /downstream/{dataset}` | 2–3 | ☐ |
| **P4** | Interop | OpenLineage bridge → graph visible in Marquez | 1–2 | ☐ |
| **P5** | **The measurement** | Ground truth precision/recall, adversarial suite, overhead numbers | 4–5 | ☐ |

## Why the adversarial suite is written at P0

It is written as failing tests *before* capture is built, so the whole sprint aims at a
fixed target instead of retrofitting a proof at the end under time pressure. This is the
single largest risk reducer for a three-week P0–P5.

## Definition of done

- [ ] `pip install dcp` + two lines instruments a Postgres+Kafka Python flow
- [ ] `docker-compose up` gives a lineage graph in Marquez in under 5 minutes
- [ ] The multi-hop trace context survives Postgres → Kafka → consumer
- [ ] The adversarial demo shows an edge OpenLineage misses and DCP catches
- [ ] Measured overhead < 1 ms p99, < 2% throughput
- [ ] Spec, quickstart, and concepts docs published under Apache 2.0

## After v1

Gap characterization — generalize the adversarial results into a *taxonomy* of why
application-layer capture misses these edges. That taxonomy, not the tool, is what the
next stage of the work builds on.

## Wanted contributions

Each is self-contained and a good first issue:
- A new DBAPI driver interceptor (MySQL, SQLite, DuckDB)
- A new emitter sink
- Additional adversarial cases — data movements you believe no catalog can see
