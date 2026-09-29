"""Ground truth: DCP's graph vs. hand-written answer keys.

Each benchmarks/ground_truth/<workload>/expected_graph.json is replayed through
DCP's real capture code (fake cursor and messages, so no infrastructure), the
events are handed to the P3 graph builder, and every level of the graph is
compared to the answer key.

The builder lives in the backend (app.graph.build). The comparison is skipped
when the backend isn't installed, so an SDK-only run doesn't hard-fail; CI
installs both packages, so it runs there.
"""

import contextvars
import json
import pathlib
from collections import deque

import pytest

from dcp import config
from dcp.interceptors.kafka import _on_consume, _on_produce
from dcp.interceptors.postgres import _capture

GROUND_TRUTH = pathlib.Path(__file__).parents[2] / "benchmarks" / "ground_truth"
WORKLOADS = sorted(p.parent.name for p in GROUND_TRUTH.glob("*/expected_graph.json"))
KAFKA_NS = "kafka://localhost:9092"


class _Info:
    host = "localhost"
    port = 5432
    dbname = "dcp"


class _Conn:
    info = _Info()


class FakeCursor:
    connection = _Conn()


class FakeMsg:
    def __init__(self, topic, headers):
        self._topic, self._headers = topic, headers

    def error(self):
        return None

    def headers(self):
        return self._headers

    def topic(self):
        return self._topic


def load(workload: str) -> dict:
    return json.loads((GROUND_TRUTH / workload / "expected_graph.json").read_text())


def datasets(key: dict) -> dict:
    return {alias: (d["namespace"], d["name"]) for alias, d in key["datasets"].items()}


def replay(key: dict, monkeypatch) -> None:
    """Run each process's steps through the real capture code, in order.

    Each process gets a fresh contextvars.Context, standing in for a separate
    OS process: the only thing that crosses between them is a record header.
    """
    records: dict = {}

    def run(steps):
        for step in steps:
            if "sql" in step:
                _capture(FakeCursor(), step["sql"])
            elif "produce" in step:
                records[step["record"]] = _on_produce(KAFKA_NS, step["produce"], None)
            elif "consume" in step:
                _on_consume(KAFKA_NS, FakeMsg(step["consume"], records[step["record"]]))

    for process in key["processes"]:
        monkeypatch.setattr(config, "_job", config.JobIdentity(process["job"], "bench", 1))
        contextvars.Context().run(run, process["steps"])


@pytest.mark.parametrize("workload", WORKLOADS)
def test_answer_key_is_well_formed(workload):
    """Every alias the key references is defined. Checks the key, not DCP."""
    key = load(workload)
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
    key = load("topic_fan_in")
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


@pytest.mark.parametrize("workload", WORKLOADS)
def test_graph_matches_answer_key(workload, events, monkeypatch):
    build = pytest.importorskip("app.graph").build
    key = load(workload)
    ds = datasets(key)
    replay(key, monkeypatch)

    g = build(events)
    assert g.datasets() == set(ds.values())
    assert g.dataset_edges() == {
        (ds[e["from"]], ds[e["to"]], e["job"]) for e in key["dataset_edges"]
    }
    assert g.run_edges() == {(e["from_job"], e["to_job"], ds[e["via"]]) for e in key["run_edges"]}
    for p in key["provenance"]:
        assert g.upstream(ds[p["dataset"]]) == {ds[a] for a in p["upstream"]}
