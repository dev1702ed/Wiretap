# Live harness (P5)

Replays every ground-truth answer key **live**: real PostgreSQL, real Kafka,
and each `process` of the key as a real, separate OS process. The result is
scored by `ground_truth/score.py`'s own row functions, exactly as the replay is.

| File | What |
|---|---|
| `seed.py` | Drops and re-creates the keys' tables in database `dcp`, and deletes and re-creates the `enriched_orders` topic with one partition. With `--key`, seeds a generated key's own `gen_*` tables (with its rows) and topics instead (P5.1). Runs **without DCP**, in its own process, so set-up never appears as lineage |
| `generate.py` | Writes each process as a plain program: a `.py` for a `script` process, an `.ipynb` (a set-up cell, then one cell per step) for a `notebook` process. psycopg and confluent-kafka calls only, **no DCP code**. A produce step logs its record's (topic, partition, offset), from the delivery callback, in the run manifest (`manifest.jsonl` in the workload's run directory). A consume step (since P5.1) looks its named record up there, **assigns that partition at that exact offset**, polls for up to 30 s, and fails loudly unless the message is that record at that offset |
| `run_live.py` | Seeds, generates, runs each script as `python -m dcp.instrument python <job>` (the `dcp-instrument` entry point) and each notebook in a Jupyter kernel with the same environment, collects the per-process JSONL, schema-checks it and scores it |

Run it through the runner: `python benchmarks/run.py --label <label> --only live`.
Everything a run produces (the programs, the executed notebook, the events and
the logs) is kept under `benchmarks/results/<label>/live/<workload>/`, so a
reader can check that the programs contain no DCP code.

**Addresses are fixed**, because the answer keys' dataset namespaces name them:
PostgreSQL at `localhost:5432` (database `dcp`, user `postgres`, password from
`DCP_PG_PASSWORD`, default `dcp`) and Kafka at `localhost:9092`. If either is
unreachable, the live stages are skipped with that reason.

**Seeding is destructive.** It drops `orders`, `refunds`, `summary`,
`refund_summary` and `daily_revenue` in database `dcp`, and deletes the
`enriched_orders` topic. The `scale` stage's live half (P5.1) also drops and
re-creates every `gen_*` table and deletes and re-creates every `gen_topic_*`
topic a generated key uses.

**Consumption by exact offset (P5.1).** P5's consumers read the earliest record
on a single-partition topic, which only identified the right record in P5's
small topologies. Now each consumer reads exactly the record the key names,
wherever it landed, so the generated keys (many producers per topic, records
consumed out of order) run live too. The run record keeps the manifest.

Dependencies: `pip install -r benchmarks/requirements.txt`.
