# The dark-zone demo (P5)

The scenario the whole project exists to show:

```
Postgres.orders
      │
      │  nightly_enrich.py  — a script nobody instrumented
      ▼
Kafka "enriched_orders"     — dcp-context header carries the trace
      │
      ▼
consumer → warehouse table
```

`nightly_enrich.py` has no framework plugin and appears in no scheduler DAG, so it is
invisible to application-layer lineage. DCP sees it because both the read and the produce
cross wires that are intercepted.

`docker-compose up` should bring up Postgres, Kafka, the DCP backend, and Marquez, run the
flow, and open the graph. **Time-to-first-graph under 5 minutes** — that is the adoption
bar for infrastructure OSS, and it is a hard requirement, not a nicety.
