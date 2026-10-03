"""Ground truth: DCP's graph vs. hand-written answer keys.

Each benchmarks/ground_truth/<workload>/expected_graph.json is replayed through
DCP's real capture code (fake cursor and messages, so no infrastructure), the
events are handed to the P3 graph builder, and every level of the graph is
compared to the answer key. The replay is benchmarks/ground_truth/harness.py,
the same one score.py uses.

The builder lives in the backend (app.graph.build). The comparison is skipped
when the backend isn't installed, so an SDK-only run doesn't hard-fail; CI
installs both packages, so it runs there.
"""

import importlib.util
import json
import pathlib
import sys
from collections import deque

import jsonschema
import pytest

from dcp import config

ROOT = pathlib.Path(__file__).parents[2]
SCHEMA = json.loads((ROOT / "spec" / "envelope.schema.json").read_text())


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        "ground_truth_harness", ROOT / "benchmarks" / "ground_truth" / "harness.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


harness = _load_harness()
WORKLOADS = harness.workloads()


@pytest.mark.parametrize("workload", WORKLOADS)
def test_answer_key_is_well_formed(workload):
    """Every alias the key references is defined. Checks the key, not DCP."""
    key = harness.load(workload)
    aliases = set(key["datasets"])
    jobs = {p["job"] for p in key["processes"]}
    for e in key["dataset_edges"]:
        assert {e["from"], e["to"]} <= aliases and e["job"] in jobs
    for e in key["run_edges"]:
        assert e["via"] in aliases and {e["from_job"], e["to_job"]} <= jobs
    for p in key["provenance"]:
        assert {p["dataset"], *p["upstream"]} <= aliases


def test_topic_fan_in_discriminates():
    """The workload must actually separate dataset-level from run-level lineage.

    Dataset-level reachability over the answer key's own edges over-approximates
    daily_revenue's provenance. If it didn't, this workload couldn't show what
    propagation adds, and would be useless as a benchmark.
    """
    key = harness.load("topic_fan_in")
    parents: dict = {}
    for e in key["dataset_edges"]:
        parents.setdefault(e["to"], set()).add(e["from"])
    reachable, queue = set(), deque(["daily_revenue"])
    while queue:
        for up in parents.get(queue.popleft(), ()):
            if up not in reachable:
                reachable.add(up)
                queue.append(up)
    (truth,) = [p for p in key["provenance"] if p["dataset"] == "daily_revenue"]
    assert set(truth["upstream"]) < reachable


def test_job_granularity_discriminates():
    """The workload must separate statement-level from job-level lineage.

    OpenLineage's core run model gives a run only its inputs and outputs, so a
    reader can take every input as feeding every output. Over this workload's
    one job, that product must imply more edges than the answer key has.
    """
    key = harness.load("job_granularity")
    (process,) = key["processes"]
    edges = [e for e in key["dataset_edges"] if e["job"] == process["job"]]
    inputs = {e["from"] for e in edges}
    outputs = {e["to"] for e in edges}
    truth = {(e["from"], e["to"]) for e in edges}
    product = {(i, o) for i in inputs for o in outputs}
    assert truth < product


@pytest.mark.parametrize("workload", WORKLOADS)
def test_replay_leaves_dcp_config_untouched(workload, events):
    """The harness swaps in its own emitter and job, and puts ours back."""
    before = config._emitter, config._job
    assert harness.replay(harness.load(workload))
    assert (config._emitter, config._job) == before
    assert events == []


@pytest.mark.parametrize("workload", WORKLOADS)
def test_graph_matches_answer_key(workload):
    build = pytest.importorskip("app.graph").build
    key = harness.load(workload)
    ds = harness.datasets(key)
    events = harness.replay(key)
    for event in events:
        jsonschema.validate(event, SCHEMA)

    g = build(events)
    assert g.datasets() == set(ds.values())
    assert g.dataset_edges() == {
        (ds[e["from"]], ds[e["to"]], e["job"]) for e in key["dataset_edges"]
    }
    assert g.run_edges() == {(e["from_job"], e["to_job"], ds[e["via"]]) for e in key["run_edges"]}
    for p in key["provenance"]:
        assert g.upstream(ds[p["dataset"]]) == {ds[a] for a in p["upstream"]}
