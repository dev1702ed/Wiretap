"""DCP -> OpenLineage -> dcp facets -> DCP is lossless, and so is the graph."""

import json

import pytest

from dcp_openlineage.reconstruct import dataset_provenance, dcp_events, implied_dataset_edges
from dcp_openlineage.translate import to_openlineage

PG = "postgres://localhost:5432"
KAFKA = "kafka://localhost:9092"
ORDERS = (PG, "dcp.public.orders")
REFUNDS = (PG, "dcp.public.refunds")
SUMMARY = (PG, "dcp.public.summary")
REFUND_SUMMARY = (PG, "dcp.public.refund_summary")
TOPIC = (KAFKA, "enriched_orders")
REVENUE = (PG, "dcp.public.daily_revenue")


def canonical(events) -> list[str]:
    return sorted(json.dumps(e, sort_keys=True) for e in events)


@pytest.fixture
def fan_in(ev):
    return [
        ev("r-orders", "read", ORDERS, "enrich_orders.py", pid=1),
        ev("w-a", "write", TOPIC, "enrich_orders.py", ["r-orders"], pid=1),
        ev(
            "r-refunds",
            "read",
            REFUNDS,
            "enrich_refunds.py",
            pid=2,
            trace_id="22222222-2222-4222-8222-222222222222",
        ),
        ev(
            "w-b",
            "write",
            TOPIC,
            "enrich_refunds.py",
            ["r-refunds"],
            pid=2,
            trace_id="22222222-2222-4222-8222-222222222222",
        ),
        ev("r-topic", "read", TOPIC, "revenue_loader.py", ["w-a"], pid=3),
        ev("w-revenue", "write", REVENUE, "revenue_loader.py", ["r-topic"], pid=3),
    ]


@pytest.fixture
def split_loader(ev):
    """job_granularity: one run, two independent INSERT ... SELECTs."""
    return [
        ev("r1", "read", ORDERS, "split_loader.py"),
        ev("w1", "write", SUMMARY, "split_loader.py", ["r1"]),
        ev("r2", "read", REFUNDS, "split_loader.py"),
        ev("w2", "write", REFUND_SUMMARY, "split_loader.py", ["r2"]),
    ]


def test_round_trip_returns_the_same_events(fan_in):
    assert canonical(dcp_events(to_openlineage(fan_in))) == canonical(fan_in)


def test_round_trip_keeps_columns(ev):
    event = ev("r", "read", ORDERS)
    event["columns"] = ["id", "total"]
    assert dcp_events(to_openlineage([event])) == [event]


def test_round_trip_rebuilds_the_same_graph(fan_in, split_loader):
    graph = pytest.importorskip("app.graph")
    for events in (fan_in, split_loader):
        original = graph.build(events)
        rebuilt = graph.build(dcp_events(to_openlineage(events)))
        assert rebuilt == original
        for ds in original.datasets():
            assert rebuilt.upstream(ds) == original.upstream(ds)


def test_without_the_facet_only_input_times_output_remains(split_loader):
    ol = to_openlineage(split_loader)
    for event in ol:
        event["run"].pop("facets", None)
    assert dcp_events(ol) == []
    assert implied_dataset_edges(ol) == {
        (src, dst, "split_loader.py")
        for src in (ORDERS, REFUNDS)
        for dst in (SUMMARY, REFUND_SUMMARY)
    }
    assert dataset_provenance(implied_dataset_edges(ol), SUMMARY) == {ORDERS, REFUNDS}


def test_implied_edges_cannot_tell_producers_apart(fan_in):
    edges = implied_dataset_edges(to_openlineage(fan_in))
    assert edges == {
        (ORDERS, TOPIC, "enrich_orders.py"),
        (REFUNDS, TOPIC, "enrich_refunds.py"),
        (TOPIC, REVENUE, "revenue_loader.py"),
    }
    assert dataset_provenance(edges, REVENUE) == {TOPIC, ORDERS, REFUNDS}


def test_provenance_terminates_on_cycles():
    edges = {(ORDERS, SUMMARY, "a"), (SUMMARY, ORDERS, "b"), (SUMMARY, SUMMARY, "c")}
    assert dataset_provenance(edges, SUMMARY) == {ORDERS}


def test_ground_truth_scores(harness):
    """The numbers benchmarks/ground_truth/score.py prints for the bridge.

    Without the facet, OpenLineage's core run model over-approximates exactly
    where the answer keys say it should; with it, the graph matches every key.
    """
    graph = pytest.importorskip("app.graph")
    for workload in harness.workloads():
        key = harness.load(workload)
        ds = harness.datasets(key)
        ol = to_openlineage(harness.replay(key))
        truth = {(ds[e["from"]], ds[e["to"]], e["job"]) for e in key["dataset_edges"]}
        implied = implied_dataset_edges(ol)
        rebuilt = graph.build(dcp_events(ol))
        assert truth <= implied
        assert rebuilt.dataset_edges() == truth
        for p in key["provenance"]:
            expected = {ds[a] for a in p["upstream"]}
            assert rebuilt.upstream(ds[p["dataset"]]) == expected
            assert expected <= dataset_provenance(implied, ds[p["dataset"]])

    key = harness.load("job_granularity")
    implied = implied_dataset_edges(to_openlineage(harness.replay(key)))
    assert len(implied) == 4  # precision 2/4
    assert dataset_provenance(implied, SUMMARY) == {ORDERS, REFUNDS}
    assert dataset_provenance(implied, REFUND_SUMMARY) == {ORDERS, REFUNDS}

    key = harness.load("topic_fan_in")
    implied = implied_dataset_edges(to_openlineage(harness.replay(key)))
    assert dataset_provenance(implied, REVENUE) == {TOPIC, ORDERS, REFUNDS}  # 2/3
