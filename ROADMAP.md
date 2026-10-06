# Roadmap

**v1 is closed** (P5.2): the final report is [`docs/results/V1.md`](docs/results/V1.md),
and the owner's remaining steps are in [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

Three-week v1 sprint. Critical path is **P0 → P1 → P2 → P5**. P3 and P4 make DCP
*usable*; P2 and P5 make it *true*. If the clock slips, P3/P4 compress — never P5.

| Phase | Goal | Deliverable | Days | Status |
|---|---|---|---|---|
| **P0** | Lock the spec | `spec/` envelope + identity scheme + JSON Schema in CI; adversarial suite written as failing tests | 1–2 | ☑ (decision 6, zero-code auto-instrumentation, closed in P5: `dcp-instrument`) |
| **P1** | Capture one protocol | `dcp.patch_psycopg()` emits schema-valid dataset events | 3–4 | ☑ |
| **P2** | Prove multi-hop | Kafka interceptor + contextvars + header propagation; 2-hop flow links | 4–5 | ☑ |
| **P3** | Queryable lineage | FastAPI ingest → networkx → `GET /downstream/{dataset}` | 2–3 | ☑ [results](docs/results/P3.md) |
| **P4** | Interop | OpenLineage bridge → graph visible in Marquez | 1–2 | ☑ [results](docs/results/P4.md) (the Marquez view is verified through the dark-zone demo: [`demo-local.md`](docs/results/demo-local.md)) |
| **P5** | **The measurement** | Ground truth precision/recall, adversarial suite, overhead numbers | 4–5 | ☑ [results](docs/results/P5.md) for the delivered instruments; owner's full-mode run done ([P5-local](docs/results/P5-local.md)): < 1 ms p99 met on every tier, < 2% throughput not met, cache-hit path only |
| **P5.1** | Harden the evidence | Cache-miss tiers and cost attribution, start-up, scaled generated ground truth | — | ☑ [results](docs/results/P5.1.md): < 1 ms p99 met on every T and L tier in the sandbox after the literal-normalised cache ([after](docs/results/P5-p51-after-final.md)); throughput not met; generated ground truth live; owner's `local-p51` run superseded by the compliant `local-final` rerun ([runs](docs/results/local-runs.md)) |
| **P5.2** | Fair baselines; close v1 | Per-process OpenLineage mapping, the stress set (DCP's failure modes, measured), limitations, evidence pack, figures, release metadata, owner runbook | — | ☑ [results](docs/results/P5.2.md), [v1 report](docs/results/V1.md) |

## Why the adversarial suite is written at P0

It is written as failing tests *before* capture is built, so the whole sprint aims at a
fixed target instead of retrofitting a proof at the end under time pressure. This is the
single largest risk reducer for a three-week P0–P5.

## Definition of done

Final states, as of v1's close (P5.2). Each item's evidence, and what would be needed to
meet it, is in [`docs/results/V1.md`](docs/results/V1.md#the-definition-of-done-final).

- [ ] `pip install dcp` + two lines instruments a Postgres+Kafka Python flow — **not met**
  as worded: instrumenting takes no lines (`dcp-instrument`) and the packages are ready,
  but the name `dcp` is taken on PyPI (publishing under another name is owner step 11)
- [x] `docker-compose up` gives a lineage graph in Marquez in under 5 minutes — **met**:
  the owner's cold run (the demo's images removed first) and warm run were both under 5
  minutes, with Marquez's API showing both jobs linked through `enriched_orders` and the
  demo exiting `0` ([`demo-local.md`](docs/results/demo-local.md)). Caveat, from the
  record: the cold run reused the locally present `apache/kafka:3.8.0` and `postgres:16`
  images, which were in use elsewhere and not removed
- [x] The multi-hop trace context survives Postgres → Kafka → consumer — **met**
- [x] The adversarial demo shows an edge OpenLineage misses and DCP catches — **met**
- [ ] Measured overhead < 1 ms p99, < 2% throughput — **half met**: < 1 ms p99 added is
  **met** on every T and L tier and every configuration — in the sandbox
  ([`P5-p51-after-final.md`](docs/results/P5-p51-after-final.md)) and on the owner's machine
  in the compliant rerun ([`P5-local-final.md`](docs/results/P5-local-final.md), evidence
  [C6](docs/paper/evidence.md#c6-overhead)). An earlier owner run, which deviated from
  runbook step 3, had four inconclusive write-tier cells; it is archived and disclosed
  ([`local-runs.md`](docs/results/local-runs.md)). < 2% throughput is **not met**
- [ ] Spec, quickstart, and concepts docs published under Apache 2.0 — **owner step
  pending**: public under Apache 2.0, the citable `v0.1.0` release is step 10

## After v1: product follow-ups

Every known limitation of v1 and the product change that would address it (store-mediated
inference, multi-record parenting, the per-call cost, the bridge's run scope and pid
reuse, and the rest) is in [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

## Wanted contributions

Each is self-contained and a good first issue:
- A new DBAPI driver interceptor (MySQL, SQLite, DuckDB)
- A new emitter sink
- Additional adversarial cases — data movements you believe no catalog can see
