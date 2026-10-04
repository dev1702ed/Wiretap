"""The profiling round's attribution (P5.1): which functions are in the call path."""

import cProfile
import pstats

import pytest
from overhead import profiling

WRAPPER = ("/repo/sdk-python/dcp/interceptors/postgres.py", 38, "execute")
ORIGINAL = ("/venv/lib/python3.12/site-packages/psycopg/cursor.py", 100, "execute")
CAPTURE = ("/repo/sdk-python/dcp/interceptors/postgres.py", 57, "_capture")
WAIT = ("/venv/lib/python3.12/site-packages/psycopg/connection.py", 479, "wait")
UUID = ("/usr/lib/python3.12/uuid.py", 723, "uuid4")
OUTSIDE = ("/repo/benchmarks/overhead/pg_worker.py", 30, "run_tier")
BUILTIN = ("~", 0, "<built-in method time.perf_counter_ns>")


def stats():
    """(cc, nc, tt, ct, callers) per function; times in seconds."""
    return {
        OUTSIDE: (1, 1, 0.01, 0.2, {}),
        BUILTIN: (200, 200, 0.001, 0.001, {OUTSIDE: (200, 200, 0.001, 0.001)}),
        WRAPPER: (100, 100, 0.001, 0.1, {OUTSIDE: (100, 100, 0.001, 0.1)}),
        ORIGINAL: (100, 100, 0.001, 0.06, {WRAPPER: (100, 100, 0.001, 0.06)}),
        WAIT: (100, 100, 0.05, 0.05, {ORIGINAL: (100, 100, 0.05, 0.05)}),
        CAPTURE: (100, 100, 0.01, 0.039, {WRAPPER: (100, 100, 0.01, 0.039)}),
        UUID: (100, 100, 0.009, 0.009, {CAPTURE: (100, 100, 0.009, 0.009)}),
    }


def test_short_names_identify_a_function_on_any_machine():
    assert profiling.short_name(WRAPPER) == "dcp/interceptors/postgres.py:38(execute)"
    assert profiling.short_name(ORIGINAL) == "psycopg/cursor.py:100(execute)"
    assert profiling.short_name(UUID) == "uuid.py:723(uuid4)"
    assert profiling.short_name(BUILTIN) == "<built-in method time.perf_counter_ns>"
    windows = ("C:\\repo\\sdk-python\\dcp\\interceptors\\postgres.py", 38, "execute")
    assert profiling.short_name(windows) == "dcp/interceptors/postgres.py:38(execute)"
    assert profiling.is_wrapper(windows)


def test_only_the_wrappers_call_path_is_ranked_per_call():
    s = profiling.summarize(stats(), calls=100)
    names = [r["function"] for r in s["top"]]
    assert names[0] == "dcp/interceptors/postgres.py:38(execute)"
    assert "benchmarks" not in " ".join(names) and "perf_counter" not in " ".join(names)
    assert s["wrapper_cumulative_us_per_call"] == pytest.approx(1000.0)
    assert s["original_cumulative_us_per_call"] == pytest.approx(600.0)
    top = {r["function"]: r for r in s["top"]}
    assert top["uuid.py:723(uuid4)"]["cumulative_us_per_call"] == pytest.approx(90.0)
    assert top["uuid.py:723(uuid4)"]["share_of_wrapper_pct"] == pytest.approx(9.0)


def test_dcps_part_excludes_the_original_call():
    s = profiling.summarize(stats(), calls=100)
    dcp = [r["function"] for r in s["dcp_top"]]
    assert dcp == ["dcp/interceptors/postgres.py:57(_capture)", "uuid.py:723(uuid4)"]


def test_a_profile_without_the_wrapper_says_so():
    assert profiling.summarize({OUTSIDE: (1, 1, 0.1, 0.1, {})}, calls=1) == {
        "calls": 1,
        "wrapper_found": False,
        "top": [],
    }


def test_a_real_cprofile_file(tmp_path):
    def execute():  # stands in for the wrapper by name; the path will not match
        return sum(range(10))

    profiler = cProfile.Profile()
    profiler.enable()
    for _ in range(5):
        execute()
    profiler.disable()
    path = tmp_path / "x.prof"
    profiler.dump_stats(str(path))
    assert pstats.Stats(str(path)).stats
    assert profiling.summarize_file(path, calls=5)["wrapper_found"] is False
