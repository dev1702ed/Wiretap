# DCP v1 — Report & Build Plan

**DCP (Data Connectivity Protocol)** — transport-layer data lineage, open source.

> One-liner: **"OpenTelemetry for data lineage."** Capture lineage where data physically
> moves (the wire), not from what applications say they did — and feed it into the lineage
> tools people already use.

---

## 1. Executive summary

Today, data lineage is captured at the **application layer**: you install a plugin inside
every tool that moves data (Spark, Airflow, dbt…) and trust it to report what it did. This
misses the "dark zones" — ad-hoc scripts, notebooks, internal services — and it's *declared*,
not *proven*.

**DCP v1** flips this. It captures lineage at the **transport layer** — the moment bytes cross
a wire (a database query, a Kafka message) — using small interceptors, and carries a
**provenance context ID** across hops so multi-step flows reconstruct automatically.

**v1 is deliberately small and honest:** two protocols (Postgres + Kafka), **table/dataset-level**
lineage only, **monitor-only** (no blocking), and it **emits standard OpenLineage** so it drops
straight into existing catalogs (Marquez, DataHub). The whole point of v1 is to *prove the core
claim*: **the network sees data movement the application layer never reports.**

---

## 2. The core thesis (recap)

- **No data moves without crossing a wire.** Every transfer is a transport event before it's an
  application event.
- So capture it at the RPC/session boundary via **interceptors**, and propagate a
  **provenance context** in protocol metadata (SQL comments, Kafka headers).
- Lineage becomes a **byproduct of communication** — covered by default, attested by evidence,
  reconstructed in real time.

---

## 3. v1 scope — what's IN and what's OUT

Being explicit here is what makes this a plan and not a wish.

| | IN for v1 | OUT of v1 (later) |
|---|---|---|
| **Protocols** | Postgres (Python DBAPI), Kafka | JDBC/Java agent, gRPC, HTTP, S3, MySQL, Snowflake |
| **Granularity** | Endpoint + **table/dataset-level** (attested). Output-column *names* free. | Column-to-column *mapping*, payload sampling |
| **Language** | **Python first** (dark zones = mostly Python scripts/notebooks) | Java, Go, Node |
| **Deployment** | In-process library (import + wrap) | Sidecar, eBPF, zero-code Java agent |
| **Mode** | **Monitor-only** (observe + emit) | Inline enforcement / blocking |
| **Interop** | Emit **OpenLineage** → Marquez/DataHub | PROV-DM export, SIEM feeds |
| **Storage** | networkx in-memory + SQLite event log | Graph DB, temporal versioning at scale |

**Why Python-first is the strategically correct choice:** the "dark zones" that application-layer
tools miss — ad-hoc scripts, notebooks, glue jobs — are overwhelmingly Python. Targeting Python
hits the exact gap that is DCP's whole reason to exist.

---

## 4. Architecture & components

Same four-layer shape as OpenTelemetry, plus the spec.

```
┌─────────────────────────────────────────────────────────────┐
│  UI / VIEW      minimal built-in graph viewer  ── OR ──       │
│                 export to Marquez UI (recommended for v1)     │
├─────────────────────────────────────────────────────────────┤
│  BACKEND        FastAPI ingest → dataset identity resolve →   │
│  (graph svc)    dedup → networkx graph → query API            │
├─────────────────────────────────────────────────────────────┤
│  COLLECTOR      pluggable emitters: console / file /          │
│  (emitter)      HTTP-to-backend / OpenLineage. Async, buffered│
├─────────────────────────────────────────────────────────────┤
│  INTERCEPTORS   dcp.patch_psycopg()  ·  dcp Kafka interceptor │
│  (the SDK)      capture + stamp/read provenance context       │
├─────────────────────────────────────────────────────────────┤
│  THE SPEC       provenance envelope + dataset identity scheme │
│                 + propagation rules (SQL comment / header)    │
└─────────────────────────────────────────────────────────────┘
```

### Components to build

| # | Component | What it does | Tech | Effort |
|---|---|---|---|---|
| 0 | **Spec** (`/spec`) | The envelope format, dataset identity scheme, propagation rules. The heart. | Markdown + JSON Schema | S |
| 1 | **Python SDK** (`/sdk-python`) | `dcp.patch_psycopg()` and Kafka interceptor. Capture events, propagate context. | Python, `contextvars`, monkeypatch | M |
| 2 | **Collector/emitter** (in SDK) | Async, non-blocking emit. Pluggable sinks: console, file, HTTP, OpenLineage. | Python, background thread/queue | S |
| 3 | **Backend** (`/backend`) | Ingest edges, resolve identity, build the graph, expose query API. | FastAPI, networkx, SQLite | M |
| 4 | **OpenLineage bridge** | Translate DCP events → OpenLineage RunEvents → Marquez. | Python | S |
| 5 | **Viewer** (`/ui`) | Show the graph. v1 = pyvis/D3 static render, *or* just use Marquez. | pyvis / HTML | S |
| 6 | **Examples + demo** (`/examples`) | docker-compose: Postgres + Kafka + DCP + Marquez + the proof script. | docker-compose | M |
| 7 | **Benchmarks** (`/benchmarks`) | Overhead measurement + the adversarial "OpenLineage-misses-this" suite. | pytest, scripts | M |

*Effort: S ≈ days, M ≈ 1–2 weeks, for one focused engineer.*

---

## 5. The provenance envelope (the spec — layer 0)

Small on purpose. Reuses **OpenLineage's identity model** (a dataset = `namespace` + `name`) so
interop is free.

```jsonc
{
  "dcp_version": "0.1",
  "trace_id":    "b7f3…",         // the lineage context — survives every hop
  "edge_id":     "e-9a1…",        // this specific transfer
  "parent":      "e-2c8…",        // upstream edge that fed this one (multi-hop link)
  "op":          "read",          // read | write
  "dataset": {
    "namespace": "postgres://prod-db:5432",   // the datasource
    "name":      "sales.public.orders"        // db.schema.table
  },
  "job": {                        // WHO moved it — this is how we light up dark zones
    "name": "nightly_enrich.py",
    "host": "analyst-vm-04",
    "pid":  48213
  },
  "ts": "2026-08-05T02:11:04Z",
  "columns": ["order_id", "customer_email", "order_total"]  // names only, free from result schema
}
```

**Dataset identity scheme:** `namespace://host:port` + `db.schema.table`.
Deterministic, dedup-able, and identical to what OpenLineage/Marquez expect.

**Propagation rules (v1):**
- **Within a process:** a Python `contextvars` value holds the current `trace_id`. When a script
  reads `orders` then writes to Kafka, both events share the trace → the edge links automatically.
- **Postgres → downstream:** inject a SQL comment (`sqlcommenter` style):
  `SELECT … /* dcp:{trace_id,parent} */`. Readable in `pg_stat_activity` and by any downstream
  DCP-aware hop.
- **Kafka → downstream:** put the envelope in a record header `dcp-context`. The consumer's
  interceptor reads it and continues the chain across the async boundary.

---

## 6. End-to-end data flow (worked example)

The exact "dark zone" scenario, instrumented:

```
[orders service] --JDBC write--> Postgres.orders
                                      │
        nightly_enrich.py  --DBAPI read (dcp.patch_psycopg)-->  (captured!)
                                      │  contextvars links read→write
                                      ▼
                          Kafka topic "enriched_orders"  (header: dcp-context)
                                      │
        spark/consumer  --read (dcp Kafka interceptor)-->  (chain continues)
                                      ▼
                              Snowflake.daily_revenue
```

- `nightly_enrich.py` is a **script nobody instrumented at the app layer** → invisible to
  OpenLineage. DCP captures it because the read and the produce **both cross wires we intercept**.
- The `trace_id` rides the Kafka header across the async gap, so the multi-hop DAG reconstructs.
- Every edge is emitted as OpenLineage → shows up in **Marquez's existing UI** with no extra work.

---

## 7. Why it's valuable (per audience)

| Audience | v1 value |
|---|---|
| **Data engineers** | Lineage for the scripts and notebooks your catalog can't see. Real impact analysis. |
| **Security / compliance** | *Attested* lineage — evidence a transfer happened, not a scheduler's intent. Basis for GDPR/DPDP audit. (Enforcement comes later; v1 proves the capture.) |
| **Platform teams** | One capture layer instead of N-per-tool plugins. Feeds the catalog you already run. |
| **The open-source community** | A neutral **provenance-context spec** — "Trace Context for data" — that any tool can adopt. This is the durable asset. |

**The single sharpest value claim v1 makes:** *"Here is a data movement that OpenLineage provably
misses, and DCP catches it — with sub-millisecond overhead."* If the demo shows that, the thesis is
proven.

---

## 8. Open-source strategy

Everything an OSS infra project needs to be adoptable:

**License:** **Apache 2.0** (same as OpenLineage, OpenTelemetry, Marquez — expected for this
category, patent-grant friendly for enterprise adoption).

**Repo layout (monorepo):**
```
dcp/
├── spec/              # the envelope + identity + propagation spec (JSON Schema + docs)
├── sdk-python/        # dcp.patch_psycopg(), Kafka interceptor, emitters
├── backend/           # FastAPI ingest + graph + query API
├── bridges/openlineage/  # DCP → OpenLineage translator
├── ui/                # minimal viewer (optional; Marquez recommended)
├── examples/          # docker-compose quickstart + the dark-zone demo
├── benchmarks/        # overhead + adversarial suite
├── docs/              # quickstart, concepts, spec reference
├── LICENSE            # Apache 2.0
├── CONTRIBUTING.md
├── CODE_OF_CONDUCT.md
└── ROADMAP.md
```

**Adoption on-ramp (must be trivial):**
- `pip install dcp` → add **two lines** to a script:
  ```python
  import dcp
  dcp.init(emit="marquez://localhost:5000")   # or console for a first look
  dcp.patch_psycopg()                          # now every query is captured
  ```
- One `docker-compose up` spins up Postgres + Kafka + DCP backend + Marquez + runs the demo and
  opens the graph. **Time-to-first-graph must be under 5 minutes** — that's the OSS adoption bar.

**Community assets:** clear `ROADMAP.md` (protocols wanted, granularity ladder), good-first-issues
(each new DBAPI driver / emitter is a self-contained contribution), and a concepts doc that teaches
the thesis (reuse this report).

**Positioning:** *complements* OpenLineage/DataHub, doesn't compete. Lead every doc with "DCP feeds
your existing catalog." That removes the rip-and-replace objection.

---

## 9. Build plan (phased)

Sequenced so **each phase produces something demonstrable**. Rough sizing for one focused engineer.

| Phase | Goal | Deliverable | ~Size |
|---|---|---|---|
| **P0 — Foundations** | Spec + repo scaffold | `/spec` envelope + identity scheme, Apache-2.0 repo, CI | ~1 wk |
| **P1 — Capture one protocol** | Prove table-level capture | `dcp.patch_psycopg()` emits correct dataset events to console | ~1–2 wk |
| **P2 — Propagation + Kafka** | Prove multi-hop | Kafka interceptor + `contextvars` + header propagation; a 2-hop flow links | ~2 wk |
| **P3 — Backend + graph** | Queryable lineage | FastAPI ingest → networkx → `GET /downstream/{dataset}` | ~1–2 wk |
| **P4 — Interop + view** | Drop into existing tools | OpenLineage bridge → Marquez; graph visible in Marquez UI | ~1 wk |
| **P5 — The proof** | Validate the thesis | Dark-zone demo + benchmark vs OpenLineage + overhead numbers | ~2 wk |

**Critical path:** P0 → P1 → P2 → P5. (P3/P4 make it *usable*; P2+P5 make it *true*.)

---

## 10. The v1 proof (evaluation — this is what makes it research, not a pitch)

Three concrete artifacts, all in `/benchmarks`:

1. **Ground-truth testbed.** A known data flow with a hand-written expected lineage graph.
   Measure DCP's **precision/recall** on edge and node recovery. Target: 100% on the covered
   protocols (it's deterministic capture, not inference).
2. **Adversarial suite.** ≥3 data movements that application-layer instrumentation **provably
   misses** — the headline being an ad-hoc script with no framework plugin. Show OpenLineage's
   graph is missing the edge and DCP's is not. *This is the money shot.*
3. **Overhead protocol.** p50/p99 added latency per intercepted call and throughput delta.
   **Target: < 1 ms p99 added latency, < 2% throughput impact** — achievable because we read the
   control path (query text + headers) and emit async, never touching result payloads.

**"Genuine finding" bar:** DCP recovers ≥1 real, useful lineage edge that OpenLineage cannot,
at < 1 ms overhead. **"Just a demo" bar:** it merely re-derives edges OpenLineage already had.

---

## 11. Explicit non-goals & honest risks (v1)

- **No column-to-column mapping.** Requires parsing transformation logic / payload → latency +
  privacy surface. Deferred. v1 gives column *names*, not column *flow*.
- **No enforcement/blocking.** Monitor-only. Inline blocking is a new production-availability risk;
  earn trust first.
- **No encrypted-payload magic.** In-process interceptor sits *above* TLS, so this is fine for v1 —
  but the sidecar/eBPF encryption problem is explicitly out of scope.
- **Unenlightened hops break the chain.** If a hop doesn't propagate the context, the multi-hop
  link is lost. v1 accepts this; the graph degrades gracefully to disconnected-but-attested edges.
- **Sampling is dangerous for lineage** (a dropped edge disconnects the graph). v1 does **no
  sampling** — capture everything on the two protocols. Scale concerns are deferred.

---

## 12. Definition of done for v1

v1 ships when **all** of these are true:

- [ ] `pip install dcp` + two lines instruments a Postgres+Kafka Python flow.
- [ ] `docker-compose up` gives a working lineage graph in Marquez in < 5 minutes.
- [ ] The multi-hop `trace_id` survives Postgres → Kafka → consumer.
- [ ] The adversarial demo shows an edge OpenLineage misses and DCP catches.
- [ ] Measured overhead < 1 ms p99, < 2% throughput.
- [ ] Spec, quickstart, and concepts docs are published under Apache 2.0.

---

*If it does those six things, DCP v1 has proven the one claim that matters: lineage belongs at the
transport layer, because the network sees what the application never reports.*
