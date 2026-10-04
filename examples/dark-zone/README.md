# The dark-zone demo (P5)

> **Run end to end once (P5.2), not yet timed by the owner.** In the P5.2 sandbox
> (Docker 29.6, Compose 5.3), `time-demo.ps1`'s warm run brought the stack up and
> Marquez's API showed `nightly_enrich.py` writing `enriched_orders` and
> `warehouse_loader.py` reading it (`docs/results/P5.2.md`, the runbook rehearsal).
> That sandbox needed its proxy's CA added to the image build, which is not part
> of the repository; CI does not run the demo. Its parts are tested elsewhere: `dcp-instrument`
> (`sdk-python/tests/test_instrument.py`), the same flow live
> (`benchmarks/live`, the `dark_zone` answer key) and the bridge
> (`bridges/openlineage/tests`). **Time-to-first-graph is measured by the owner**
> with `time-demo.ps1` (`docs/RUNBOOK.md`, step 7), which writes its own record.

The scenario the whole project exists to show:

```
Postgres.orders
      │
      │  nightly_enrich.py  — a script nobody instrumented
      ▼
Kafka "enriched_orders"     — dcp-context header carries the trace
      │
      ▼
warehouse_loader.py → Postgres.daily_revenue
```

`nightly_enrich.py` has no framework plugin, appears in no scheduler DAG, and
contains **no DCP code**. Application-layer lineage cannot see it. DCP does,
because `dcp-instrument` intercepts the read and the produce on the wire, and the
Kafka record header carries the trace to the consumer.

The v1 bar: **`docker compose up` to a lineage graph in Marquez in under 5
minutes.**

## What runs

| Service | What | Host port |
|---|---|---|
| `postgres` | PostgreSQL 16, database `dcp` | none |
| `kafka` | Apache Kafka 3.8.0, KRaft, single node | none |
| `marquez-db` | Marquez's own PostgreSQL 14 | none |
| `marquez` | Marquez API 0.51.1 | **5000** |
| `marquez-web` | Marquez web UI 0.51.1 | **3000** |
| `demo` | Built from this repo (`Dockerfile`): waits for the others, seeds the data (no DCP), runs `nightly_enrich.py` then `warehouse_loader.py` under `dcp-instrument`, posts the lineage with `python -m dcp_openlineage --post http://marquez:5000`, and exits | none |

Only Marquez's UI (3000) and API (5000) are published, so this does not clash
with your own Postgres on 5432 or Kafka on 9092. **It does clash with
`examples/marquez` on 3000 and 5000:** stop that one first
(`docker compose -f examples/marquez/docker-compose.yml down`).

## Run it and time it (Windows PowerShell)

From the repository root, with Docker Desktop running:

```powershell
# 0. Optional, for a "warm" timing: pull and build first, then time from step 1.
#    Skip this to time a cold first run (image downloads included).
# docker compose -f examples/dark-zone/docker-compose.yml pull
# docker compose -f examples/dark-zone/docker-compose.yml build

# 1. Start the clock and bring everything up.
$start = Get-Date
docker compose -f examples/dark-zone/docker-compose.yml up -d --build

# 2. Poll the Marquez API until both jobs are there: the graph is visible.
$ns = [uri]::EscapeDataString("dcp://dark-zone-demo")
do {
    Start-Sleep -Seconds 2
    try {
        $jobs = (Invoke-RestMethod "http://localhost:5000/api/v1/namespaces/$ns/jobs").jobs
    } catch { $jobs = @() }
} until ($jobs.Count -ge 2)
$elapsed = (Get-Date) - $start
"Time to first graph: {0:N0} s" -f $elapsed.TotalSeconds

# 3. Look at it.
Start-Process "http://localhost:3000"
```

If step 2 never finishes, look at the demo's log:

```powershell
docker compose -f examples/dark-zone/docker-compose.yml logs demo
```

Report the number from step 2, and whether it was a cold run (images
downloaded) or a warm one (step 0 done first). Both are worth knowing; the bar
is about the cold one.

## What the graph should show

In the web UI at http://localhost:3000, choose the namespace
**`dcp://dark-zone-demo`** (the demo container's hostname):

- two jobs, **`nightly_enrich.py`** and **`warehouse_loader.py`**;
- `dcp.public.orders` (namespace `postgres://postgres:5432`) → `nightly_enrich.py`
  → **`enriched_orders`** (namespace `kafka://kafka:9092`) →
  `warehouse_loader.py` → `dcp.public.daily_revenue`;
- each job's latest run carries the `dcp` run facet: the DCP events behind it,
  shown as JSON.

Dataset namespaces name the hosts as the scripts saw them inside the compose
network (`postgres`, `kafka`), not `localhost`.

## Clean up

```powershell
docker compose -f examples/dark-zone/docker-compose.yml down -v
```

## Files

| File | What |
|---|---|
| `docker-compose.yml` | The services above, with pinned image tags |
| `Dockerfile` | The `demo` image: SDK and bridge installed from the repo; strips CRs from the scripts it copies |
| `Dockerfile.dockerignore` | Keeps the build context (the repository root) down to the SDK, the bridge and this directory |
| `run-demo.sh` | The `demo` entrypoint (LF line endings, enforced by `.gitattributes`) |
| `wait_for.py` | Waits for Postgres, Kafka and the Marquez API |
| `seed.py` | Creates `orders` (three rows), `daily_revenue` and the `enriched_orders` topic. No DCP code |
| `nightly_enrich.py`, `warehouse_loader.py` | The two plain scripts. No DCP code |
