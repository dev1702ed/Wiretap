# DCP lineage in Marquez (P4)

> **UNVERIFIED IN CI.** Nothing in this directory is run by CI, and it was written
> without a Docker, Postgres, Kafka or Marquez to test against. The bridge itself
> is tested (`bridges/openlineage/tests`, against the official OpenLineage schema
> and a stub HTTP server); this example only wires it to a real Marquez. If a step
> fails, please note which one.

What you will see: two jobs, `nightly_enrich.py` and `warehouse_loader.py`,
connected through the Kafka topic `enriched_orders`, in the Marquez web UI.

| Service | Port on your machine |
|---|---|
| Marquez lineage API (the bridge POSTs here) | **5000** — `http://localhost:5000` |
| Marquez admin / healthcheck | 5001 |
| Marquez web UI | **3000** — `http://localhost:3000` |
| Marquez's own Postgres | *not published*, so it does not clash with your Postgres on 5432 |

## What you need

- Docker Desktop, with `docker compose`.
- Python 3.10 or newer.
- Your own Postgres on `localhost:5432` and Kafka on `localhost:9092` (the same ones
  the scratch scripts used). The scripts read `DCP_PG_DSN` and `DCP_KAFKA` if your
  connection details differ from the defaults
  (`postgresql://postgres:postgres@localhost:5432/dcp` and `localhost:9092`).

All commands are **Windows PowerShell**, run from the repository root unless a step
says otherwise.

## 1. Start Marquez

```powershell
docker compose -f examples/marquez/docker-compose.yml up -d
docker compose -f examples/marquez/docker-compose.yml ps
```

Wait until the `api` service is running, then check the API answers (an empty list
of namespaces is fine on a fresh install):

```powershell
Invoke-RestMethod http://localhost:5000/api/v1/namespaces
```

The first start pulls the images and runs Marquez's database migrations; give it a
minute.

## 2. Record lineage with DCP

Create a virtual environment and install the SDK (with the Postgres and Kafka
extras) and the bridge:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e "./sdk-python[postgres,kafka]" -e ./bridges/openlineage
```

From `examples/marquez`, set up the tables once, then run the producer and then
the consumer. `seed.py` is deliberately not instrumented, so creating the data
does not show up as lineage. The other two call
`dcp.init(emit="file://dcp_events.jsonl")`, so both append to the same file there:

```powershell
cd examples/marquez
# Only if your Postgres/Kafka differ from the defaults:
# $env:DCP_PG_DSN = "postgresql://USER:PASSWORD@localhost:5432/DBNAME"
# $env:DCP_KAFKA  = "localhost:9092"
python seed.py
python nightly_enrich.py
python warehouse_loader.py
Get-Content dcp_events.jsonl
```

`seed.py` creates `orders` (with two rows, unless it already has some) and
`order_totals`. `nightly_enrich.py` reads `orders` and produces each row to
`enriched_orders`; `warehouse_loader.py` consumes `enriched_orders` and writes
each record to `order_totals`. You should see read and write events from both
scripts, sharing one `trace_id` (the Kafka `dcp-context` header carried it
across). The consumer stops after ten seconds without new records.

## 3. Send it to Marquez

```powershell
python -m dcp_openlineage --events dcp_events.jsonl --post http://localhost:5000
```

It prints how many OpenLineage events it sent (a `START` and a `COMPLETE` per run)
and exits non-zero if any could not be delivered. On a first run against an empty
topic that is `posted 4 OpenLineage events (2 runs)`. Records already on the
topic from earlier runs, with their own traces, add runs of `warehouse_loader.py`. To look
at the events without sending them:

```powershell
python -m dcp_openlineage --events dcp_events.jsonl --out openlineage.jsonl
```

Re-sending is safe: run IDs are deterministic, so the same events update the same
runs.

## 4. Look at the graph

Open **http://localhost:3000**.

- Jobs are in the namespace `dcp://<your computer name>`; pick it from the namespace
  drop-down at the top.
- Open the job `nightly_enrich.py`. Its lineage graph shows
  `orders` → `nightly_enrich.py` → `enriched_orders` → `warehouse_loader.py` →
  `order_totals`: the two jobs connected through `enriched_orders`.
- Datasets keep their DCP names: Postgres tables are `DBNAME.public.orders` in the
  namespace `postgres://localhost:5432`, and the topic is `enriched_orders` in
  `kafka://localhost:9092`.
- Each run's `COMPLETE` event carries a `dcp` run facet with the DCP events behind
  it. Marquez shows it as JSON on the run; it does not draw edges from it (see
  [`docs/decisions/openlineage-mapping.md`](../../docs/decisions/openlineage-mapping.md)).

## Clean up

```powershell
docker compose -f examples/marquez/docker-compose.yml down -v
Remove-Item examples/marquez/dcp_events.jsonl, examples/marquez/openlineage.jsonl -ErrorAction SilentlyContinue
```

`down -v` also deletes Marquez's database volume.

## Files

| File | What |
|---|---|
| `docker-compose.yml` | Marquez API, web UI and database, pinned to 0.51.1 / `postgres:14`, based on Marquez's official compose files |
| `init-db.sh` | Creates Marquez's database and user. Copied unchanged from Marquez 0.51.1 (Apache-2.0) |
| `seed.py` | Creates `orders` and `order_totals`. Not instrumented |
| `nightly_enrich.py` | The producer (`scratch_produce.py`-style) |
| `warehouse_loader.py` | The consumer (`scratch_consume.py`-style) |
| `.gitattributes` | Keeps `init-db.sh` in LF line endings on Windows checkouts, so bash can run it |
