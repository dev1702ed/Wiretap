# The DCP Spec (P0)

The envelope, the dataset identity scheme, and the propagation rules. This is the layer
everything else depends on — and the most durable artifact in the repo.

Status: **DRAFT v0.1.** Decisions 1–5 are closed (§4); decision 6 is open.

---

## 1. The provenance envelope

```jsonc
{
  "dcp_version": "0.1",
  "trace_id":    "…",      // constant for an entire multi-hop flow
  "edge_id":     "…",      // this specific transfer
  "parent":      ["…"],    // upstream edge_ids that fed this one ([] at flow origin)
  "op":          "read",   // read | write
  "dataset": {
    "namespace": "postgres://prod-db:5432",
    "name":      "sales.public.orders"
  },
  "job": {
    "name": "nightly_enrich.py",
    "host": "analyst-vm-04",
    "pid":  48213
  },
  "ts": "2026-09-16T02:11:04Z",
  "columns": ["order_id", "customer_email", "order_total"]
}
```

**ID semantics (the part that makes multi-hop work):**
- `trace_id` is constant across every hop of one logical flow. Two unrelated flows never
  share one.
- `edge_id` + `parent` form the DAG *within* that flow. `parent` is a list: N inputs
  can feed one output (fan-in), which the concept brief names as a hard case.
- Without this split you cannot distinguish "two hops of one flow" from "two unrelated
  flows" — which is the whole multi-hop claim.

Normative schema: `envelope.schema.json`. CI validates every emitted event against it.

## 2. Dataset identity

`namespace` + `name`, deliberately identical to OpenLineage's model so interop is free.

| Source | namespace | name |
|---|---|---|
| Postgres | `postgres://host:port` | `db.schema.table` |
| Kafka | `kafka://broker:port` | `topic` |

Must be deterministic — the same physical dataset reached two ways must resolve to one
node, or the graph fragments.

## 3. Propagation rules

| Hop | Channel | Mechanism |
|---|---|---|
| Within a process | `contextvars` | Current trace/edge state held per-task |
| Postgres | SQL comment | sqlcommenter format, trace only: `SELECT … /*dcp_trace='…'*/` |
| Kafka | Record header | `dcp-context` header (KIP-82), JSON: `{"trace": "…", "parent": ["…"]}` |

**Where each channel's context goes.** The SQL comment reaches the Postgres *server*:
it is visible in `pg_stat_activity`, in server logs, and to pgaudit. It does **not** reach
later readers of the table, because rows carry no per-record metadata — a process that
reads the rows tomorrow cannot learn who wrote them. That is why Postgres reads have
`parent: []` in v1. A Kafka header, by contrast, is stored with the record and travels
with it to every consumer, so a consume is parented to the producer's write: the only
attested cross-process link in v1.

**Protocols with no metadata channel:** v1 accepts context loss. The chain breaks, the
graph degrades to disconnected-but-attested edges. This is a stated limitation, not a bug
— and it is one of the things a protocol-native design would not have.

## 4. Decisions (closed)

| # | Decision | Options | Resolution |
|---|---|---|---|
| 1 | ID format | UUIDv7 / ULID / UUID4 | **UUID4 now** (stdlib on every supported Python). UUIDv7 is the documented upgrade path, to match OpenLineage's run-ID convention; IDs are opaque to every consumer, so the switch is safe at any time |
| 2 | `op` enum | `read`/`write` only, or add txn ops | **`read`/`write` only** — do not add ops with no consumer |
| 3 | Kafka namespace | `kafka://broker:port` vs cluster ID | **`kafka://broker:port`** — consistent with Postgres |
| 4 | `job` capture | At `init()` vs per-event | **At `init()`** — `os.getpid()`, `socket.gethostname()` once, reused |
| 5 | Schema draft | draft-07 vs 2020-12 | **Draft 2020-12** |
| 6 | Zero-code auto-instrumentation | Explicit `dcp.init()` + `dcp.patch_*()` calls vs. instrumenting a script without editing it | **Open.** Would remove the `patch_kafka()` import-order hazard and strengthen adversarial cases 1–2 from "declared vs. attested" to "no code changes at all" |

## 5. Compatibility

- **OpenLineage**: identity model reused directly; `bridges/openlineage/` translates events.
- **PROV-DM**: out of scope for v1; note the mapping, do not build it.
