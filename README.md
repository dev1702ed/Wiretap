# DCP — Data Connectivity Protocol

**Transport-layer data lineage.** Capture lineage where data physically moves — the wire —
not from what applications report they did.

> One-liner: *"OpenTelemetry for data lineage."*

---

## What this repo is

DCP is a **measurement instrument**. Its purpose is to answer one question with numbers:

> How much real data movement do application-layer lineage systems (OpenLineage, DataHub,
> Atlas) structurally fail to see?

Everything in this repo exists to produce that measurement credibly. The SDK, the backend,
and the OpenLineage bridge are apparatus; `/benchmarks` is the product.

## The claim v1 makes

*"Here is a data movement that OpenLineage provably misses, DCP catches it, and the
overhead is under 1 ms p99."*

If the benchmarks show that, the thesis holds. If DCP merely re-derives edges OpenLineage
already had, it is a demo, not a finding. That distinction is enforced in
`benchmarks/README.md`.

## How it works

1. **Intercept** at the session boundary — `dcp.patch_psycopg()` wraps the Postgres DBAPI;
   a Kafka interceptor wraps produce/consume.
2. **Propagate** a provenance context across hops using metadata channels the protocols
   already have — a SQL comment for Postgres, a record header for Kafka.
3. **Emit** standard OpenLineage so the graph lands in tooling people already run (Marquez,
   DataHub), rather than asking anyone to adopt a new catalog.

## v1 scope

| | IN | OUT (later) |
|---|---|---|
| Protocols | Postgres (Python DBAPI), Kafka | JDBC, gRPC, HTTP, S3, MySQL |
| Granularity | Table/dataset-level (attested); column *names* only | Column-to-column mapping |
| Language | Python | Java, Go, Node |
| Deployment | In-process library | Sidecar, eBPF |
| Mode | Monitor-only | Inline enforcement / blocking |
| Storage | networkx in-memory + SQLite event log | Graph DB, temporal versioning |

Why Python first: the dark zones application-layer tools miss — ad-hoc scripts, notebooks,
glue jobs — are overwhelmingly Python. That is precisely the gap being measured.

## Quickstart

> Not yet functional — scaffold only. See ROADMAP.md for phase status.

```python
import dcp
dcp.init(emit="console")
dcp.patch_psycopg()
# every query is now captured
```

## Layout

| Path | What | Phase |
|---|---|---|
| `spec/` | Provenance envelope, dataset identity, propagation rules | P0 |
| `sdk-python/` | Interceptors, context propagation, emitters | P1–P2 |
| `backend/` | Ingest, identity resolution, graph, query API | P3 |
| `bridges/openlineage/` | DCP events → OpenLineage RunEvents | P4 |
| `examples/dark-zone/` | docker-compose demo of the gap scenario | P5 |
| `benchmarks/` | Ground truth, adversarial suite, overhead protocol | P0 + P5 |

## Non-goals (v1)

- No column-to-column mapping — requires payload/transformation parsing.
- No enforcement or blocking — monitor-only; inline blocking is a new availability risk.
- No sampling — a dropped edge disconnects the graph, which is not true of tracing.
- Unenlightened hops break the chain; the graph degrades to disconnected-but-attested edges.

## License

Apache 2.0.
