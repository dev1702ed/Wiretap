"""DCP -> OpenLineage: schema validity, the run mapping, determinism."""

import itertools
import uuid

import pytest

from dcp_openlineage import RUN_EVENT_SCHEMA_URL
from dcp_openlineage.translate import DCP_RUN_NAMESPACE, to_openlineage

PG = "postgres://localhost:5432"
KAFKA = "kafka://localhost:9092"
ORDERS = (PG, "dcp.public.orders")
REFUNDS = (PG, "dcp.public.refunds")
TOPIC = (KAFKA, "enriched_orders")
REVENUE = (PG, "dcp.public.daily_revenue")
TRACE_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
TRACE_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def runs(ol_events) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for event in ol_events:
        out.setdefault(event["run"]["runId"], []).append(event)
    return out


@pytest.fixture
def dark_zone(ev):
    """Producer and consumer: two processes, one trace, linked by a header."""
    return [
        ev("r1", "read", ORDERS, "nightly_enrich.py", pid=10, ts="2026-09-16T02:00:00+00:00"),
        ev(
            "w1",
            "write",
            TOPIC,
            "nightly_enrich.py",
            ["r1"],
            pid=10,
            ts="2026-09-16T02:00:01+00:00",
        ),
        ev(
            "r2",
            "read",
            TOPIC,
            "warehouse_loader.py",
            ["w1"],
            pid=20,
            ts="2026-09-16T02:05:00+00:00",
        ),
        ev(
            "w2",
            "write",
            REVENUE,
            "warehouse_loader.py",
            ["r2"],
            pid=20,
            ts="2026-09-16T02:05:02+00:00",
        ),
    ]


def test_every_event_is_valid_openlineage_and_every_facet_is_valid(dark_zone, validate):
    ol = to_openlineage(dark_zone)
    validate(ol)
    assert all(event["schemaURL"] == RUN_EVENT_SCHEMA_URL for event in ol)


def test_one_process_is_one_run(ev, validate):
    events = [
        ev("r", "read", ORDERS, ts="2026-09-16T02:00:00+00:00"),
        ev("w", "write", TOPIC, parent=["r"], ts="2026-09-16T02:00:05+00:00"),
    ]
    ol = to_openlineage(events)
    validate(ol)
    assert [event["eventType"] for event in ol] == ["START", "COMPLETE"]
    assert len(runs(ol)) == 1
    start, complete = ol
    assert start["eventTime"] == "2026-09-16T02:00:00+00:00"
    assert complete["eventTime"] == "2026-09-16T02:00:05+00:00"
    for event in ol:
        assert event["job"] == {"namespace": "dcp://host-a", "name": "job.py"}
        assert event["inputs"] == [{"namespace": PG, "name": "dcp.public.orders"}]
        assert event["outputs"] == [{"namespace": KAFKA, "name": "enriched_orders"}]
    assert "facets" not in start["run"]
    facet = complete["run"]["facets"]["dcp"]
    assert [e["edge_id"] for e in facet["events"]] == ["r", "w"]
    assert facet["events"][1]["parent"] == ["r"]


def test_producer_and_consumer_sharing_a_trace_are_two_runs(dark_zone, validate):
    ol = to_openlineage(dark_zone)
    validate(ol)
    by_run = runs(ol)
    assert len(by_run) == 2
    jobs = {events[0]["job"]["name"] for events in by_run.values()}
    assert jobs == {"nightly_enrich.py", "warehouse_loader.py"}
    traces = {e["run"]["facets"]["dcp"]["trace_id"] for e in ol if e["eventType"] == "COMPLETE"}
    assert traces == {"11111111-1111-4111-8111-111111111111"}


def test_long_running_consumer_with_two_traces_is_two_runs_of_one_job(ev, validate):
    events = [
        ev("ra", "read", TOPIC, "loader.py", ["wa"], trace_id=TRACE_A),
        ev("wa2", "write", REVENUE, "loader.py", ["ra"], trace_id=TRACE_A),
        ev("rb", "read", TOPIC, "loader.py", ["wb"], trace_id=TRACE_B),
        ev("wb2", "write", REVENUE, "loader.py", ["rb"], trace_id=TRACE_B),
    ]
    ol = to_openlineage(events)
    validate(ol)
    by_run = runs(ol)
    assert len(by_run) == 2
    assert {(e["job"]["namespace"], e["job"]["name"]) for e in ol} == {
        ("dcp://host-a", "loader.py")
    }


def test_same_script_on_two_hosts_is_two_jobs(ev):
    ol = to_openlineage([ev("a", "read", ORDERS, host="h1"), ev("b", "read", ORDERS, host="h2")])
    assert {e["job"]["namespace"] for e in ol} == {"dcp://h1", "dcp://h2"}


def test_run_id_is_stable_across_re_exports(dark_zone):
    first = to_openlineage(dark_zone)
    again = to_openlineage([dict(event) for event in dark_zone])
    assert first == again
    expected = str(
        uuid.uuid5(
            DCP_RUN_NAMESPACE,
            "11111111-1111-4111-8111-111111111111|host-a|10|nightly_enrich.py",
        )
    )
    assert first[0]["run"]["runId"] == expected


def test_run_namespace_constant_never_changes():
    """Changing it would change every runId ever exported."""
    assert str(DCP_RUN_NAMESPACE) == "0c8af99c-3a1d-5111-8bf3-3ed587595f51"


def test_every_permutation_translates_identically(dark_zone):
    reference = to_openlineage(dark_zone)
    for order in itertools.permutations(dark_zone):
        assert to_openlineage(list(order)) == reference


def test_identical_duplicates_count_once(dark_zone):
    assert to_openlineage(dark_zone + [dict(e) for e in dark_zone]) == to_openlineage(dark_zone)


def test_inputs_and_outputs_are_unique_and_sorted(ev, validate):
    events = [
        ev("r1", "read", REFUNDS),
        ev("r2", "read", ORDERS),
        ev("r3", "read", ORDERS),
        ev("w1", "write", REVENUE, parent=["r1"]),
        ev("w2", "write", TOPIC, parent=["r2"]),
    ]
    ol = to_openlineage(events)
    validate(ol)
    assert [d["name"] for d in ol[0]["inputs"]] == ["dcp.public.orders", "dcp.public.refunds"]
    assert [d["namespace"] for d in ol[0]["outputs"]] == [KAFKA, PG]


def test_missing_host_and_z_timestamps(validate):
    event = {
        "dcp_version": "0.1",
        "trace_id": TRACE_A,
        "edge_id": "e",
        "op": "read",
        "dataset": {"namespace": PG, "name": "dcp.public.orders"},
        "job": {"name": "job.py"},
        "ts": "2026-09-16T02:11:04Z",
    }
    ol = to_openlineage([event])
    validate(ol)
    assert ol[0]["job"]["namespace"] == "dcp://unknown-host"
    assert ol[0]["eventTime"] == "2026-09-16T02:11:04+00:00"


def test_unparseable_timestamp_fails_loudly(ev):
    with pytest.raises(ValueError, match="unparseable ts"):
        to_openlineage([ev("e", "read", ORDERS, ts="yesterday")])


def test_ground_truth_workloads_translate_to_valid_openlineage(harness, validate):
    """Real capture output, replayed through the shared harness."""
    for workload in harness.workloads():
        validate(to_openlineage(harness.replay(harness.load(workload))))
