"""Attribution from the P5.1 profiling round: cProfile, inside the call path. P5.1.

pg_worker.py --profile dumps one cProfile file per tier, recorded over the timed
loop only. This module reads one and keeps the functions reached from DCP's
psycopg wrapper (`execute` in dcp/interceptors/postgres.py), the instrumented
call path, ranked by cumulative time, normalised per timed call.

cProfile adds its own cost to every function call, so its absolute times are
inflated, and inflated most where many small functions run. Use these tables to
say WHERE the time goes (attribution), never HOW MUCH it is (magnitude): the
timed rounds give the magnitudes. Named profiling.py, not profile.py, so it
never shadows the stdlib module cProfile imports.
"""

import collections
import pstats

TOP = 15
WRAPPER = ("dcp/interceptors/postgres.py", "execute")
ORIGINAL = ("psycopg/cursor.py", "execute")  # what the wrapper calls through to


def _path(filename: str) -> str:
    return filename.replace("\\", "/")


def short_name(func: tuple) -> str:
    """file:line(function), with the path cut to what identifies it anywhere."""
    filename, line, name = func
    if filename == "~":
        return name  # a built-in, e.g. <built-in method time.perf_counter_ns>
    path = _path(filename)
    for marker in ("/site-packages/", "/sdk-python/", "/benchmarks/"):
        if marker in path:
            path = path.split(marker, 1)[1]
            break
    else:
        parts = path.split("/")
        if len(parts) >= 2 and parts[-2].startswith("python3"):
            path = parts[-1]  # the standard library
        elif "/lib/python3" in path:
            path = path.split("/lib/", 1)[1].split("/", 1)[1]
        else:
            path = "/".join(parts[-2:])
    return f"{path}:{line}({name})"


def _is(func: tuple, which: tuple) -> bool:
    filename, _line, name = func
    return name == which[1] and _path(filename).endswith(which[0])


def is_wrapper(func: tuple) -> bool:
    return _is(func, WRAPPER)


def reachable(stats: dict, roots, avoid=()) -> set:
    """Every function called, directly or not, from `roots`, not walking
    through any function in `avoid`."""
    children = collections.defaultdict(set)
    for func, (_cc, _nc, _tt, _ct, callers) in stats.items():
        for caller in callers:
            children[caller].add(func)
    avoid = set(avoid)
    seen, todo = set(roots), list(roots)
    while todo:
        for child in children[todo.pop()]:
            if child not in seen and child not in avoid:
                seen.add(child)
                todo.append(child)
    return seen


def _rows(stats: dict, funcs, calls: int, wrapper_ct: float, top: int) -> list[dict]:
    ranked = sorted(funcs, key=lambda f: (-stats[f][3], short_name(f)))[:top]
    rows = []
    for func in ranked:
        _cc, nc, tt, ct, _callers = stats[func]
        rows.append(
            {
                "function": short_name(func),
                "calls_per_call": nc / calls,
                "own_us_per_call": tt * 1e6 / calls,
                "cumulative_us_per_call": ct * 1e6 / calls,
                "share_of_wrapper_pct": 100 * ct / wrapper_ct if wrapper_ct else None,
            }
        )
    return rows


def summarize(stats: dict, calls: int, top: int = TOP) -> dict:
    """The top functions in the wrapper's call path, per timed call."""
    roots = [f for f in stats if is_wrapper(f)]
    if not roots:
        return {"calls": calls, "wrapper_found": False, "top": []}
    wrapper_ct = sum(stats[f][3] for f in roots)
    originals = [f for f in stats if _is(f, ORIGINAL)]
    original_ct = sum(stats[f][3] for f in originals)
    # DCP's part: everything the wrapper reaches without going through the
    # original execute. A function called on both sides (json, uuid, ...) is
    # one entry in cProfile, so its row counts both; such rows are rare here.
    dcp_only = reachable(stats, roots, avoid=originals) - set(roots)
    return {
        "calls": calls,
        "wrapper_found": True,
        "wrapper_cumulative_us_per_call": wrapper_ct * 1e6 / calls,
        "original_cumulative_us_per_call": original_ct * 1e6 / calls,
        "top": _rows(stats, reachable(stats, roots), calls, wrapper_ct, top),
        "dcp_top": _rows(stats, dcp_only, calls, wrapper_ct, top),
    }


def summarize_file(path, calls: int, top: int = TOP) -> dict:
    return summarize(pstats.Stats(str(path)).stats, calls, top)
