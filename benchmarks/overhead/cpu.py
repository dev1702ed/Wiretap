"""4a: the CPU cost of capture, with no database. P5.

    python benchmarks/overhead/cpu.py --out cpu.json

Times DCP's `_capture` on a fake cursor with a discarding emitter, and
`_classify` on its own (sqlglot's share), for every query tier: 1,000 warm-up
calls, then 10,000 timed calls, each timed with time.perf_counter_ns.
Reported in microseconds. Run it once per Python: run.py does, for every
interpreter it is given.

Each tier runs in a fresh contextvars.Context that has already captured one
point read, so a write (T3) has an earlier read to be parented to: job-level
parenting, as in a script that reads, then writes.

The emitter discards events, so this is capture alone: parsing, identity,
parenting, event construction. Serialising and delivering an event is the
sink's cost, measured live in 4b.

The L tiers (added in P5.1) send a different text on every call, warm-up
included, so every call misses the parse cache's exact-text level: the texts
are built before timing starts, and each timed call gets the next one.

Where the SDK has it (P5.1 O1 onwards), the literal-normalisation pass that
builds the cache's second-level key is also timed on its own, per tier.
"""

import argparse
import contextvars
import importlib.metadata
import json
import platform
import sys
import time

from queries import TIERS, literal_texts
from stats import summarize

WARMUP = 1_000
TIMED = 10_000


class NullEmitter:
    """Discards every event. Benchmark-only, deliberately not part of the SDK."""

    def emit(self, event) -> None:
        return None

    def flush(self, timeout: float = 5.0) -> None:
        return None


class _Info:
    host = "localhost"
    port = 5432
    dbname = "dcp"


class _Conn:
    info = _Info()


class FakeCursor:
    connection = _Conn()


def _time(fn, query, warmup: int, timed: int) -> list[int]:
    for _ in range(warmup):
        fn(query)
    samples = []
    clock = time.perf_counter_ns
    for _ in range(timed):
        start = clock()
        fn(query)
        samples.append(clock() - start)
    return samples


def _time_each(fn, texts_warm: list[str], texts_timed: list[str]) -> list[int]:
    """Like _time, but call k gets its own text: a literal tier's distinct texts."""
    for text in texts_warm:
        fn(text)
    samples = []
    clock = time.perf_counter_ns
    for text in texts_timed:
        start = clock()
        fn(text)
        samples.append(clock() - start)
    return samples


def _timer(tier, warmup: int, timed: int):
    """time(fn) -> samples, for this tier: the same text, or a new text per call."""
    if not tier.literal:
        return lambda fn: _time(fn, tier.query, warmup, timed)
    warm = literal_texts(tier, warmup)
    texts = literal_texts(tier, timed, start=warmup)
    return lambda fn: _time_each(fn, warm, texts)


def _timer_offset(tier, warmup: int, timed: int):
    """A literal tier's timer over texts numbered after the first timer's."""
    start = warmup + timed
    warm = literal_texts(tier, warmup, start=start)
    texts = literal_texts(tier, timed, start=start + warmup)
    return lambda fn: _time_each(fn, warm, texts)


def run(warmup: int = WARMUP, timed: int = TIMED) -> dict:
    from dcp import config
    from dcp.interceptors import postgres
    from dcp.interceptors.postgres import _capture, _classify

    cache_key = getattr(postgres, "_cache_key", None)  # P5.1 O1 onwards

    cursor = FakeCursor()
    point_read = TIERS[0].query
    saved = config._emitter, config._job, config._propagate_sql
    config._emitter = NullEmitter()
    config._job = config.JobIdentity("cpu_bench.py", "bench", 1)
    config._propagate_sql = False
    tiers = {}
    try:
        for tier in TIERS:
            timer = _timer(tier, warmup, timed)

            def capture_samples(timer=timer):
                _capture(cursor, point_read)  # an earlier read, for job-level parenting
                return timer(lambda q: _capture(cursor, q))

            capture = contextvars.Context().run(capture_samples)
            # A literal tier's texts were all just parsed once by capture: rebuild
            # the timer with texts it has not seen, so classify misses the cache too.
            classify = (
                _timer_offset(tier, warmup, timed)(_classify)
                if tier.literal
                else timer(_classify)
            )
            tiers[tier.name] = {
                "label": tier.label,
                "capture_us": summarize(capture, scale=1000),
                "classify_us": summarize(classify, scale=1000),
            }
            if cache_key is not None:  # P5.1 O1: the normalisation pass alone
                tiers[tier.name]["normalize_us"] = summarize(
                    timer(cache_key), scale=1000
                )
    finally:
        config._emitter, config._job, config._propagate_sql = saved
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
        "sqlglot": importlib.metadata.version("sqlglot"),
        "warmup": warmup,
        "timed": timed,
        "tiers": tiers,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="4a: CPU cost of DCP capture")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(run(), f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
