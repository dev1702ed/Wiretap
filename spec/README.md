# The DCP Spec (P0)

The envelope, the dataset identity scheme, and the propagation rules. This is the layer
everything else depends on — and the most durable artifact in the repo.

Status: **DRAFT — open decisions below must be closed before P1 starts.**

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

**Protocols with no metadata channel:** v1 accepts context loss. The chain breaks, the
graph degrades to disconnected-but-attested edges. This is a stated limitation, not a bug
— and it is one of the things a protocol-native design would not have.

## 4. Open decisions (close before P1)

| # | Decision | Options | Lean |
|---|---|---|---|
| 1 | ID format | UUIDv7 / ULID / UUID4 | **UUIDv7** — OpenLineage recommends it for run IDs; matching them is worth more than ULID's ergonomics |
| 2 | `op` enum | `read`/`write` only, or add txn ops | **read/write only** — do not add ops with no consumer |
| 3 | Kafka namespace | `kafka://broker:port` vs cluster ID | `kafka://broker:port` — consistent with Postgres |
| 4 | `job` capture | At `init()` vs per-event | **At `init()`** — `os.getpid()`, `socket.gethostname()` once, reused |
| 5 | Schema draft | draft-07 vs 2020-12 | 2020-12 unless tooling objects |

## 5. Compatibility

- **OpenLineage**: identity model reused directly; `bridges/openlineage/` translates events.
- **PROV-DM**: out of scope for v1; note the mapping, do not build it.
