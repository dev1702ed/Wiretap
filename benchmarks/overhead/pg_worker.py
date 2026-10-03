"""4b worker: times psycopg calls against live Postgres. Plain: no DCP code. P5.

    python pg_worker.py OUT.json WARMUP CALLS            (configuration `base`)
    dcp-instrument python pg_worker.py OUT.json ...      (every other configuration)

The same program runs in every configuration; only the environment differs.
Per tier: WARMUP calls discarded, then CALLS calls, each timed as
cursor.execute(query, params) plus fetchall() where the tier returns rows,
with time.perf_counter_ns. Throughput is CALLS over the wall time of the timed
loop. The password comes from PGPASSWORD (libpq).
"""

import json
import sys
import time

import psycopg
from queries import PG_CONNINFO, TIERS


def run_tier(cursor, tier, warmup: int, calls: int) -> dict:
    for i in range(warmup):
        cursor.execute(tier.query, tier.params(i))
        if tier.returns_rows:
            cursor.fetchall()
    clock = time.perf_counter_ns
    samples = []
    started = clock()
    for i in range(calls):
        t0 = clock()
        cursor.execute(tier.query, tier.params(i))
        if tier.returns_rows:
            cursor.fetchall()
        samples.append(clock() - t0)
    return {"ns": samples, "elapsed_ns": clock() - started}


def main(argv: list[str]) -> int:
    out, warmup, calls = argv[0], int(argv[1]), int(argv[2])
    results = {}
    with psycopg.connect(PG_CONNINFO, autocommit=True) as conn:
        cursor = conn.cursor()
        for tier in TIERS:
            results[tier.name] = run_tier(cursor, tier, warmup, calls)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
