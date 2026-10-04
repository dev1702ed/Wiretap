"""4b worker: times psycopg calls against live Postgres. Plain: no DCP code. P5.

    python pg_worker.py OUT.json WARMUP CALLS            (configuration `base`)
    dcp-instrument python pg_worker.py OUT.json ...      (every other configuration)
    ... OUT.json WARMUP CALLS --profile PREFIX --tiers T1,L1   (P5.1 profiling round)

The same program runs in every configuration; only the environment differs.
Per tier: WARMUP calls discarded, then CALLS calls, each timed as
cursor.execute(query, params) plus fetchall() where the tier returns rows,
with time.perf_counter_ns. Throughput is CALLS over the wall time of the timed
loop. The password comes from PGPASSWORD (libpq).

A literal tier (P5.1) sends a different text on every call: its warm-up and
timed calls are numbered consecutively, and the texts are built before the
timed loop, so formatting them is not timed.

--profile runs only the named tiers, each timed loop under cProfile, and dumps
PREFIX.<tier>.prof. Those rounds attribute cost; their timings are never used
(cProfile inflates them).
"""

import json
import sys
import time

import psycopg
from queries import PG_CONNINFO, TIERS


def run_tier(cursor, tier, warmup: int, calls: int, profiler=None) -> dict:
    if tier.literal:
        warm = [tier.statement(n) for n in range(warmup)]
        timed = [tier.statement(warmup + n) for n in range(calls)]
        return _run_literal(cursor, tier, warm, timed, profiler)
    for i in range(warmup):
        cursor.execute(tier.query, tier.params(i))
        if tier.returns_rows:
            cursor.fetchall()
    clock = time.perf_counter_ns
    samples = []
    if profiler is not None:
        profiler.enable()
    started = clock()
    for i in range(calls):
        t0 = clock()
        cursor.execute(tier.query, tier.params(i))
        if tier.returns_rows:
            cursor.fetchall()
        samples.append(clock() - t0)
    elapsed = clock() - started
    if profiler is not None:
        profiler.disable()
    return {"ns": samples, "elapsed_ns": elapsed}


def _run_literal(cursor, tier, warm, timed, profiler) -> dict:
    for query, params in warm:
        cursor.execute(query, params)
        if tier.returns_rows:
            cursor.fetchall()
    clock = time.perf_counter_ns
    samples = []
    if profiler is not None:
        profiler.enable()
    started = clock()
    for query, params in timed:
        t0 = clock()
        cursor.execute(query, params)
        if tier.returns_rows:
            cursor.fetchall()
        samples.append(clock() - t0)
    elapsed = clock() - started
    if profiler is not None:
        profiler.disable()
    return {"ns": samples, "elapsed_ns": elapsed}


def main(argv: list[str]) -> int:
    out, warmup, calls = argv[0], int(argv[1]), int(argv[2])
    profile_prefix, only = None, None
    rest = argv[3:]
    while rest:
        flag, value, rest = rest[0], rest[1], rest[2:]
        if flag == "--profile":
            profile_prefix = value
        elif flag == "--tiers":
            only = value.split(",")
        else:
            raise SystemExit(f"unknown option {flag}")
    tiers = [t for t in TIERS if only is None or t.name in only]
    results = {}
    with psycopg.connect(PG_CONNINFO, autocommit=True) as conn:
        cursor = conn.cursor()
        for tier in tiers:
            profiler = None
            if profile_prefix is not None:
                import cProfile

                profiler = cProfile.Profile()
            results[tier.name] = run_tier(cursor, tier, warmup, calls, profiler)
            if profiler is not None:
                profiler.dump_stats(f"{profile_prefix}.{tier.name}.prof")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
