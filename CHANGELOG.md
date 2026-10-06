# Changelog

All notable changes to DCP. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the three packages (`dcp`, `dcp-backend`, `dcp-openlineage`) share one version.

## [0.1.0] - v1

The first release: transport-layer lineage capture for Python (Postgres and Kafka),
a queryable lineage graph, an OpenLineage bridge, and the benchmarks that measure what
application-layer lineage misses. Each phase below links its results report; every
number lives in those reports and the records they cite, not here.

### Added

- **P0 — the spec.** The provenance envelope, dataset identity and propagation rules,
  with a JSON Schema checked in CI, and the adversarial suite written first, as failing
  tests. See [`spec/README.md`](spec/README.md); P0–P2 have no results report of their
  own: their capture is measured from P3 on.
- **P1 — capture one protocol.** `dcp.patch_psycopg()` wraps the Postgres DBAPI and
  emits a schema-valid read or write event per dataset a statement touches.
- **P2 — multi-hop.** The Kafka interceptor, context propagation through `contextvars`,
  and the `dcp-context` record header, so a consumer's events link to the producer's
  write across processes; the opt-in SQL trace comment.
- **P3 — queryable lineage.** The backend: an append-only SQLite event log, a lineage
  graph rebuilt exactly by replaying it, run-level and dataset-level provenance, and an
  HTTP API; the file and non-blocking HTTP emitters; the shared replay harness and
  `score.py`. [Results](docs/results/P3.md).
- **P4 — interop.** `dcp-openlineage`, a batch bridge from DCP events to OpenLineage
  RunEvents valid against the official schema, with a `dcp` run facet that keeps the
  attested edges; the `job_granularity` answer key; the Marquez example.
  [Results](docs/results/P4.md).
- **P5 — the measurement.** Zero-code instrumentation (`dcp-instrument`), the live
  harness (real Postgres, Kafka and OS processes), the adversarial suite demonstrated
  live with the OpenLineage baseline measured, overhead and CPU benchmarks, the parse
  cache, the CI live job and the one-command dark-zone demo.
  [Results](docs/results/P5.md).
- **P5.1 — hardening.** Cache-miss (literal) tiers, cost attribution and profiling,
  start-up work, a literal-normalised parse cache, pinned benchmark environments, and
  ground truth at scale from a seeded generator, live and in replay.
  [Results](docs/results/P5.1.md).
- **P5.2 — fair baselines and closing v1.** The bridge's `process` run scope (one
  OpenLineage run per process, as OpenLineage itself reports it; the default is
  unchanged); generator 1.1 and the stress set, which measures DCP's two known failure
  modes (multi-record consumers, store-mediated reads) apart from every other result;
  `docs/LIMITATIONS.md`; the paper evidence pack (`benchmarks/evidence.py`) and figures
  (`benchmarks/figures.py`); this changelog, `CITATION.cff` and the owner's runbook.
  [Results](docs/results/P5.2.md), [v1 report](docs/results/V1.md).
- **The owner's final runs.** The full-mode benchmark runs on the owner's machine, each
  with its protocol status; the first final run deviated from the runbook and is archived
  byte-for-byte beside its compliant rerun. [Runs index](docs/results/local-runs.md).
- **The demo record.** The dark-zone demo timed cold and warm, with Marquez's API checked
  for both jobs linked through `enriched_orders`. [Record](docs/results/demo-local.md).

### Fixed

- `benchmarks/evidence.py` printed each table's Source line above the table, directly
  under the previous one; it now follows its own table, with a test.

### Known limitations

Every known limitation and its product follow-up: [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

[0.1.0]: https://github.com/dev1702ed/Wiretap/releases/tag/v0.1.0
