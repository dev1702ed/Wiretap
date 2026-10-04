"""Score DCP's lineage graph against the ground-truth answer keys.

    python benchmarks/ground_truth/score.py

For each workload: precision and recall for nodes, dataset edges, run edges,
and each provenance entry (definitions in README.md in this directory). Every
provenance entry is scored twice: run-level (`upstream`, following parent
links over events) and a dataset-level baseline (`dataset_upstream`,
reachability over dataset edges), which is what lineage without propagation
can do.

Each workload also gets an OpenLineage translation section (P4): the same
events translated by the bridge (bridges/openlineage), then read back two ways
(reconstruct.py). `openlineage dataset edges` and `openlineage provenance` are
what OpenLineage's core run model implies (every input of a run feeds every
output); `openlineage + dcp facet provenance` rebuilds the backend graph from
the `dcp` run facets and asks it.

Since P5.2 each workload also gets a per-process OpenLineage section: the same
events translated with the bridge's `process` run scope (one run per process,
as a real OpenLineage integration reports it), read back with the core model:
`openlineage (per process) dataset edges` and `openlineage (per process)
provenance(...)`. It is printed after the existing sections, so every line
printed before P5.2 is unchanged.

The events come from harness.replay: DCP's real capture code with faked
database and broker I/O. These are not live runs. The scoring is independent
of where the events come from (`score_all(events_for)`): benchmarks/live runs
the same keys against real Postgres and Kafka and scores them with these
same functions.

Needs both packages installed: pip install -e ./sdk-python -e ./backend
The bridge has no dependencies; it is imported from bridges/openlineage when it
is not installed.
"""

import pathlib
import sys

from harness import datasets, load, replay, workloads

try:
    from app.graph import build
except ImportError:
    sys.exit("score.py needs the DCP backend installed: pip install -e ./backend")

try:
    import dcp_openlineage  # noqa: F401
except ImportError:
    sys.path.insert(
        0, str(pathlib.Path(__file__).resolve().parents[2] / "bridges" / "openlineage")
    )

from dcp_openlineage.reconstruct import (
    dataset_provenance,
    dcp_events,
    implied_dataset_edges,
)
from dcp_openlineage.translate import to_openlineage


def ratio(hits: int, total: int) -> str:
    return f"{hits}/{total} = {hits / total:.3f}" if total else f"{hits}/{total} = n/a"


def _namer(ds: dict):
    alias = {d: a for a, d in ds.items()}

    def name(d):
        return alias.get(d, f"{d[0]}/{d[1]}")

    def names(found):
        return [name(d) for d in found]

    return name, names


def rows(key: dict, events: list[dict]):
    """Yield (label, found, expected, render) for every level of one workload."""
    ds = datasets(key)
    name, names = _namer(ds)
    g = build(events)

    yield "nodes", g.datasets(), set(ds.values()), names
    yield (
        "dataset edges",
        g.dataset_edges(),
        {(ds[e["from"]], ds[e["to"]], e["job"]) for e in key["dataset_edges"]},
        lambda edges: [f"{name(a)}->{name(b)} ({job})" for a, b, job in edges],
    )
    yield (
        "run edges",
        g.run_edges(),
        {(e["from_job"], e["to_job"], ds[e["via"]]) for e in key["run_edges"]},
        lambda edges: [f"{a}->{b} via {name(via)}" for a, b, via in edges],
    )
    for p in key["provenance"]:
        target, expected = ds[p["dataset"]], {ds[a] for a in p["upstream"]}
        yield f"upstream({p['dataset']}) run-level", g.upstream(target), expected, names
        yield (
            f"upstream({p['dataset']}) dataset-level baseline",
            g.dataset_upstream(target),
            expected,
            names,
        )


def openlineage_rows(key: dict, events: list[dict]):
    """The same, for the events after translation to OpenLineage."""
    ds = datasets(key)
    name, names = _namer(ds)
    ol = to_openlineage(events)
    implied = implied_dataset_edges(ol)
    rebuilt = build(dcp_events(ol))

    yield (
        "openlineage dataset edges",
        implied,
        {(ds[e["from"]], ds[e["to"]], e["job"]) for e in key["dataset_edges"]},
        lambda edges: [f"{name(a)}->{name(b)} ({job})" for a, b, job in edges],
    )
    for p in key["provenance"]:
        target, expected = ds[p["dataset"]], {ds[a] for a in p["upstream"]}
        yield (
            f"openlineage provenance({p['dataset']})",
            dataset_provenance(implied, target),
            expected,
            names,
        )
    for p in key["provenance"]:
        target, expected = ds[p["dataset"]], {ds[a] for a in p["upstream"]}
        yield (
            f"openlineage + dcp facet provenance({p['dataset']})",
            rebuilt.upstream(target),
            expected,
            names,
        )


def openlineage_process_rows(key: dict, events: list[dict]):
    """OpenLineage's core model over the bridge's `process` run scope (P5.2)."""
    ds = datasets(key)
    name, names = _namer(ds)
    implied = implied_dataset_edges(to_openlineage(events, run_scope="process"))

    yield (
        "openlineage (per process) dataset edges",
        implied,
        {(ds[e["from"]], ds[e["to"]], e["job"]) for e in key["dataset_edges"]},
        lambda edges: [f"{name(a)}->{name(b)} ({job})" for a, b, job in edges],
    )
    for p in key["provenance"]:
        target, expected = ds[p["dataset"]], {ds[a] for a in p["upstream"]}
        yield (
            f"openlineage (per process) provenance({p['dataset']})",
            dataset_provenance(implied, target),
            expected,
            names,
        )


def measure(levels) -> list[dict]:
    """The rows as data: label, hits, found and expected counts, and notes."""
    out = []
    for label, found, expected, render in levels:
        notes = [f"+{x}" for x in sorted(render(found - expected))]
        notes += [f"-{x}" for x in sorted(render(expected - found))]
        out.append(
            {
                "label": label,
                "hits": len(found & expected),
                "found": len(found),
                "expected": len(expected),
                "notes": notes,
            }
        )
    return out


LEVEL_WIDTH = 52


def format_table(measured: list[dict], width: int = LEVEL_WIDTH) -> list[str]:
    lines = [f"{'level':<{width}}{'precision':<16}{'recall':<16}notes"]
    for row in measured:
        line = (
            f"{row['label']:<{width}}{ratio(row['hits'], row['found']):<16}"
            f"{ratio(row['hits'], row['expected']):<16}{' '.join(row['notes'])}"
        )
        lines.append(line.rstrip())
    return lines


def fitted_table(measured: list[dict]) -> list[str]:
    """format_table, its level column widened to the longest label if needed.
    For the per-process section only: the older sections keep their width."""
    longest = max((len(row["label"]) for row in measured), default=0)
    return format_table(measured, max(LEVEL_WIDTH, longest + 1))


def score_workload(key: dict, events: list[dict]) -> dict:
    """Every level of one workload, for DCP's graph and for the OpenLineage
    translation in both of the bridge's run scopes."""
    return {
        "workload": key["workload"],
        "dcp": measure(rows(key, events)),
        "openlineage": measure(openlineage_rows(key, events)),
        "openlineage_per_process": measure(openlineage_process_rows(key, events)),
    }


def score_all(events_for, names: list[str] | None = None) -> list[dict]:
    """Score each workload, taking its events from `events_for(key)`: replay or live."""
    results = []
    for name in workloads() if names is None else names:
        key = load(name)
        results.append(score_workload(key, events_for(key)))
    return results


REPLAY_INTRO = "Replays DCP's real capture code with faked database and broker I/O; not a live run."


def report_lines(results: list[dict], intro: str = REPLAY_INTRO) -> list[str]:
    lines = [
        "DCP ground-truth score",
        intro,
        "precision = |found & expected| / |found|    recall = |found & expected| / |expected|",
    ]
    for result in results:
        workload = result["workload"]
        lines += ["", f"== {workload}", *format_table(result["dcp"]), ""]
        lines.append(
            f"-- {workload}: OpenLineage translation (core run model, then with the dcp facet)"
        )
        lines += format_table(result["openlineage"])
        if "openlineage_per_process" in result:
            lines += [
                "",
                (
                    f"-- {workload}: OpenLineage translation, one run per process "
                    "(core run model; added in P5.2)"
                ),
                *fitted_table(result["openlineage_per_process"]),
            ]
    return lines


def main() -> int:
    print("\n".join(report_lines(score_all(replay))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
