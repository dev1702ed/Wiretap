# Overhead protocol (P5)

What DCP costs the code it observes, measured two ways. Every number comes from
`python benchmarks/run.py --label <label> [--quick]`, rendered into
`docs/results/P5-<label>.md`; nothing is typed by hand.

## Targets

- < 1 ms p99 added latency per intercepted call
- < 2% throughput loss

## 4a. CPU microbenchmark (`cpu.py`): capture alone, no database

DCP's `_capture` on a fake cursor, with a `NullEmitter` that discards events
(defined in the benchmark, not the SDK), and `_classify` alone, which isolates
sqlglot's share. For each tier: **1,000 warm-up calls, then 10,000 timed calls**,
each timed with `time.perf_counter_ns`. Reported as p50, p95, p99 and p99.9 in
µs. Each tier runs in a fresh `contextvars.Context` that has already captured one
point read, so a write has a read to be parented to (job-level parenting). Run
once per Python (`--cpu-python`, repeatable).

This isolates capture: parsing, identity, parenting and event construction.
Serialising and delivering an event is the sink's cost, measured in 4b.

## The query tiers (`queries.py`, fixed)

| Tier | Query |
|---|---|
| T1 point read | `SELECT id, total FROM orders WHERE id = %s` |
| T2 join | `orders` joined to `refunds` on `id`, filtered by `id` |
| T3 insert values | `INSERT INTO summary VALUES (%s, %s)`: job-level parenting |
| T4 insert-select | `INSERT INTO summary SELECT id, total FROM orders WHERE id = %s` |
| T5 analytical | A 45-line query: three CTEs, a join, window functions, aggregates. Written once, before any timing, and not changed after |

## 4b. Live per-call overhead (`latency.py`)

Real PostgreSQL and Kafka on localhost, seeded by `live/seed.py`.

| Config | DCP | Sink |
|---|---|---|
| `base` | none | — |
| `file` | `dcp-instrument` | `file://` (a temp file) |
| `http` | `dcp-instrument` | `http://` to a **live backend**: `create_app` under uvicorn, one worker, a fresh temp database each round |
| `http-down` | `dcp-instrument` | `http://` to a port that is bound but never listens, so the emitter's worker fails and retries the whole time: `emit()` must stay non-blocking |
| `file+sqlcomment` | `dcp-instrument`, `DCP_PROPAGATE_SQL=1` | `file://` |

Method:

- The timed program, `pg_worker.py`, is the **same plain program in every
  configuration** (no DCP code); only its environment differs.
- Each configuration runs as a **fresh process per round**. Rounds alternate the
  configurations in the fixed order `base, file, http, http-down,
  file+sqlcomment` to cancel drift.
- **Full mode: 10 rounds × 2,000 calls per tier**, 200 warm-up calls per tier per
  round discarded. **Quick mode: 5 × 300**, warm-up 50.
- Per call: `cursor.execute(q, params)` plus `fetchall()` where the tier returns
  rows, timed with `time.perf_counter_ns`. Throughput: calls per second over the
  round's timed loop.
- Process start-up is excluded from per-call timing and reported separately:
  `python -c pass` plain, under `dcp-instrument`, and with only DCP's
  `sitecustomize` (no wrapper process).
- **Kafka:** `kafka_worker.py` times each `produce()` call for 1 KB messages in
  `base`, `file` and `http`: 10,000 messages per round (quick: 2,000) after a
  warm-up, then `flush()`. Throughput includes the flush.
- **Delivery is counted, not assumed:** lines in the file sink; the backend's
  event count for `http`.

Statistics (`stats.py`):

- Per configuration and tier: p50, p95, p99 and p99.9 over every timed call
  (linear interpolation between ranks).
- **Added latency** (`instrumented − base`) for p50 and p99, and **throughput
  change %**, are **paired by round** and given a **95% bootstrap confidence
  interval** over rounds (10,000 resamples, fixed seed).
- **Verdict** per tier and configuration, against each target: **met** (the whole
  interval is below the target), **not met** (the whole interval is at or above
  it), **inconclusive** (the interval straddles it).

Backpressure (reported, not a target): `backpressure_worker.py` runs the
`http-down` case with an 8-event queue and reports the emitter's exact `dropped`
count, and per-call latency, which must stay under the worker's 50 ms retry
backoff: a blocked `emit()` would show it. This one worker is DCP-aware on
purpose, because `dcp-instrument` has no queue-size setting.

## Where the numbers come from

| Source | Role |
|---|---|
| The sandbox (`docs/results/P5-sandbox*.md`) | 4a, definitive for its machine; 4b on a shared cloud VM |
| CI (`--label ci --quick`, job summary) | Noisy shared runners: **not** an authoritative overhead source |
| The owner's machine (`docs/results/P5-local.md`) | The authoritative full-mode 4b numbers |

## Do not

- Measure against an idle console emitter and call it production overhead.
- Report a mean. The p99 is the number that decides whether anyone deploys this.
- Change an iteration count, a tier or a configuration after seeing results.
