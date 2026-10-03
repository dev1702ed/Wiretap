# Live harness (P5)

Replays every ground-truth answer key **live**: real PostgreSQL, real Kafka,
and each `process` of the key as a real, separate OS process. The result is
scored by `ground_truth/score.py`'s own row functions, exactly as the replay is.

| File | What |
|---|---|
| `seed.py` | Drops and re-creates the keys' tables in database `dcp`, and deletes and re-creates the `enriched_orders` topic with one partition. Runs **without DCP**, in its own process, so set-up never appears as lineage |
| `generate.py` | Writes each process as a plain program: a `.py` for a `script` process, an `.ipynb` (a set-up cell, then one cell per step) for a `notebook` process. psycopg and confluent-kafka calls only, **no DCP code**. A consume step polls for up to 30 s with a consumer group unique to the run, and fails loudly unless the record it reads is the one the key names |
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
`enriched_orders` topic.

Dependencies: `pip install -r benchmarks/requirements.txt`.
