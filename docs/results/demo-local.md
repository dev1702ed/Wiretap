# Dark-zone demo: time to first graph (`demo-local`)

Written by `examples/dark-zone/time_demo.py` (run by `time-demo.ps1`, docs/RUNBOOK.md step 7). Do not edit by hand: re-run it.

|  |  |
|---|---|
| Started (UTC) | 2026-10-05T17:41:38+00:00 |
| Git commit | `fe54bc5b2d861c09019959c4ae40d218515642cf` |
| Working tree dirty | True |
| OS | Windows-11-10.0.26200-SP0 |
| Docker server | 29.8.0 |
| Docker Compose | 5.5.1 |
| Compose file | `examples/dark-zone/docker-compose.yml` |

## Images

| Image (tag) | Image ID after the runs |
|---|---|
| `apache/kafka:3.8.0` | `sha256:c89f315cff96` |
| `dcp-dark-zone-demo` | `sha256:181f18d71923` |
| `marquezproject/marquez-web:0.51.1` | `sha256:7312112ca0e6` |
| `marquezproject/marquez:0.51.1` | `sha256:0721c976cff1` |
| `postgres:14` | `sha256:c2427de38f99` |
| `postgres:16` | `sha256:a3b7f434b2dc` |

## Timings

From `docker compose up -d --build` to Marquez showing both jobs linked through `enriched_orders` (polled every 2 s). The v1 bar is under 300 s.

| Run | Before the run | Seconds to the graph | Under 5 minutes | Demo exit code | Both jobs linked through `enriched_orders` (Marquez API) |
|---|---|---|---|---|---|
| cold | the demo's images removed first (still present, in use elsewhere: `apache/kafka:3.8.0`, `postgres:16`) | 196.9 | yes | 0 | yes |
| warm | every image present; containers and volumes removed first | 17.4 | yes | 0 | yes |

## Marquez API check

**cold**: jobs in `dcp://dark-zone-demo`: `nightly_enrich.py`, `warehouse_loader.py`; `nightly_enrich.py` outputs: `kafka://kafka:9092` `enriched_orders`; `warehouse_loader.py` inputs: `kafka://kafka:9092` `enriched_orders`.

**warm**: jobs in `dcp://dark-zone-demo`: `nightly_enrich.py`, `warehouse_loader.py`; `nightly_enrich.py` outputs: `kafka://kafka:9092` `enriched_orders`; `warehouse_loader.py` inputs: `kafka://kafka:9092` `enriched_orders`.
