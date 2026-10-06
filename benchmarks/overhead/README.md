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
| L1 point read, literal (**added in P5.1**) | T1 with the id inlined: `... WHERE id = <n>` |
| L3 insert values, literal (**added in P5.1**) | T3 with both values inlined: `INSERT INTO summary VALUES (<n>, <n % 97>.5)` |
| L5 analytical, literal (**added in P5.1**) | T5 with its one numeric literal inlined: `net_total >= -<n>` (keeps every row, as T5's `0` does) |

**The L tiers were added in P5.1, after P5's results were seen.** Each uses a
different literal on **every** call, warm-up included (`<n>` is the call's
number in its process), so the query text never repeats and every call misses
DCP's parse cache, which is keyed on the query text. That is the shape of an
ad-hoc script that builds SQL with `f"... WHERE id = {x}"`, and the path P5's
parameterised tiers never measured. They make the benchmark harder; T1–T5 are
unchanged. In 4a the texts are built before timing starts; in 4b
`pg_worker.py` builds them before each timed loop, so formatting is never
timed. L1's ids above 4 match no row, as such ids would; L5 returns T5's rows.

## 4b. Live per-call overhead (`latency.py`)

Real PostgreSQL and Kafka on localhost, seeded by `live/seed.py`.

| Config | DCP | Sink |
|---|---|---|
| `base` | none | — |
| `file` | `dcp-instrument` | `file://` (a temp file) |
| `http` | `dcp-instrument` | `http://` to a **live backend**: `create_app` under uvicorn, one worker, a fresh temp database each round |
| `http-down` | `dcp-instrument` | `http://` to a port that is bound but never listens, so the emitter's worker fails and retries the whole time: `emit()` must stay non-blocking |
| `file+sqlcomment` | `dcp-instrument`, `DCP_PROPAGATE_SQL=1` | `file://` |
| `wrap-only` (**added in P5.1**) | `dcp-instrument`, `DCP_CAPTURE=off` | `null://` (nothing is emitted) |
| `capture-null` (**added in P5.1**) | `dcp-instrument` | `null://`: every event is built, then discarded |

**The two ablations were added in P5.1, after P5's results were seen**, to
attribute the per-call cost on the real psycopg path. `DCP_CAPTURE=off` keeps
DCP's wrappers installed but skips capture (it is also an operational kill
switch); `null://` is a diagnostic sink that constructs every event and
delivers none. Paired by round, so `base` cancels:

| Component | Measured as |
|---|---|
| wrapper | `wrap-only` |
| capture + construction | `capture-null − wrap-only` |
| async enqueue | `http-down − capture-null` |
| synchronous file write | `file − http-down` |
| SQL comment | `file+sqlcomment − file` |

The renderer prints this attribution for every tier (and, for Kafka, wrapper,
capture + construction, enqueue to the live backend `http − capture-null`, and
the file write `file − capture-null`), by per-round p50 and by the implied cost
below, each with a bootstrap interval.

**Profiling round (P5.1).** One extra round per instrumented configuration, on
T1 and L1 only, with `pg_worker.py --profile`: each timed loop runs under
`cProfile` and `profiling.py` ranks the top 15 functions by cumulative time
among those reached from DCP's psycopg wrapper (the whole call path, which
includes the original `execute`), and again for DCP's part alone. It is never
used for a timing: cProfile inflates absolute times. It says where the time
goes, not how much.

Method:

- The timed program, `pg_worker.py`, is the **same plain program in every
  configuration** (no DCP code); only its environment differs.
- Each configuration runs as a **fresh process per round**. Rounds alternate the
  configurations in the fixed order `base, file, http, http-down,
  file+sqlcomment, wrap-only, capture-null` to cancel drift (the last two since P5.1).
- **Full mode: 10 rounds × 2,000 calls per tier**, 200 warm-up calls per tier per
  round discarded. **Quick mode: 5 × 300**, warm-up 50.
- Per call: `cursor.execute(q, params)` plus `fetchall()` where the tier returns
  rows, timed with `time.perf_counter_ns`. Throughput: calls per second over the
  round's timed loop.
- Process start-up is excluded from per-call timing and reported separately:
  `python -c pass` plain, under `dcp-instrument`, and with only DCP's
  `sitecustomize` (no wrapper process); and, added in P5.1,
  `python -c "import psycopg, confluent_kafka"` plain and under
  `dcp-instrument`, for a program that does use the libraries.
- **Kafka:** `kafka_worker.py` times each `produce()` call for 1 KB messages in
  `base`, `file` and `http` (and, since P5.1, `wrap-only` and `capture-null`): 10,000 messages per round (quick: 2,000) after a
  warm-up, then `flush()`. Throughput includes the flush.
- **Delivery is counted, not assumed:** lines in the file sink; the backend's
  event count for `http`.

Statistics (`stats.py`):

- Per configuration and tier: p50, p95, p99 and p99.9 over every timed call
  (linear interpolation between ranks).
- **Added latency** (`instrumented − base`) for p50 and p99, and **throughput
  change %**, are **paired by round** and given a **95% bootstrap confidence
  interval** over rounds (10,000 resamples, fixed seed).
- **Implied added µs per call (P5.1):** `1e6/throughput_instrumented −
  1e6/throughput_base`, paired by round, with the same bootstrap. Computed by
  the code, never by hand. It turns a throughput percentage, which depends on
  how fast the query itself is, into the machine-portable fixed cost per call.
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
| The owner's machine, P5 (`docs/results/P5-local.md`) | The authoritative full-mode 4b numbers for the P5 code |
| The P5.1 sandbox (`docs/results/P5-p51-*.md`) | Same-machine before/after pairs for P5.1's optimisations, with the L tiers, ablations, attribution and profile; comparable only with each other |
| The owner's machine, final code (`docs/results/P5-local-final.md`; it superseded the planned `P5-local-p51.md`; its runs: `docs/results/local-runs.md`) | The authoritative full-mode numbers for the final code |

## Do not

- Measure against an idle console emitter and call it production overhead.
- Report a mean. The p99 is the number that decides whether anyone deploys this.
- Change an iteration count, a tier or a configuration after seeing results.
