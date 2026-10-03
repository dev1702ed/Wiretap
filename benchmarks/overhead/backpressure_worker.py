"""4b backpressure check: the http sink with nowhere to send, and a tiny queue. P5.

    python backpressure_worker.py OUT.json URL QUEUE_SIZE WARMUP CALLS

Unlike the other workers this one is DCP-aware, on purpose: dcp-instrument has
no setting for the queue size, so it calls dcp.init() itself and swaps in an
HTTPEmitter with a QUEUE_SIZE-event queue pointed at URL, a closed port. Then
it runs the T1 point read WARMUP times untimed, then CALLS times, timing each
call, and reports the exact number of events the emitter dropped. emit() must
never block: per-call latency should stay bounded although every event is
dropped.
"""

import json
import sys
import time

import dcp
import psycopg
from dcp import config
from dcp.emitters.http import HTTPEmitter
from queries import PG_CONNINFO, TIERS


def main(argv: list[str]) -> int:
    out, url, queue_size = argv[0], argv[1], int(argv[2])
    warmup, calls = int(argv[3]), int(argv[4])
    dcp.init(emit=url)
    config._emitter.close(timeout=0.1)
    emitter = HTTPEmitter(url, queue_size=queue_size, max_retries=1, backoff=0.05)
    config._emitter = emitter
    dcp.patch_psycopg()
    tier = TIERS[0]
    clock = time.perf_counter_ns
    samples = []
    with psycopg.connect(PG_CONNINFO, autocommit=True) as conn:
        cursor = conn.cursor()
        for i in range(warmup):
            cursor.execute(tier.query, tier.params(i))
            cursor.fetchall()
        for i in range(calls):
            t0 = clock()
            cursor.execute(tier.query, tier.params(i))
            cursor.fetchall()
            samples.append(clock() - t0)
    emitter.close(timeout=2.0)
    result = {
        "ns": samples,
        "queue_size": queue_size,
        "events_emitted": (warmup + calls) * tier.events_per_call,
        "dropped": emitter.dropped,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
