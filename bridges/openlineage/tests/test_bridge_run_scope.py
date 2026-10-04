"""The run-scope option (P5.2, A1): `process` maps one OpenLineage run per
process; `trace-process`, the default, is unchanged.

Every row of the case matrix in docs/tasks/P5.2.md (A2) has a test here, named
`test_a2_<row>_...`, in both modes where the row applies. Each test passes
`run_scope=` explicitly, so on code without the option every test fails on its
own rather than the file failing to import.
"""

import itertools
import json
import pathlib
import uuid

import pytest

from dcp_openlineage.__main__ import main
from dcp_openlineage.reconstruct import dataset_provenance, dcp_events, implied_dataset_edges
from dcp_openlineage.translate import DCP_RUN_NAMESPACE, to_openlineage

PG = "postgres://localhost:5432"
KAFKA = "kafka://localhost:9092"
ORDERS = (PG, "dcp.public.orders")
REFUNDS = (PG, "dcp.public.refunds")
TOPIC = (KAFKA, "enriched_orders")
REVENUE = (PG, "dcp.public.daily_revenue")
SUMMARY = (PG, "dcp.public.summary")
TRACE_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
TRACE_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
TRACE_C = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
SCOPES = ("trace-process", "process")


def runs(ol_events) -> dict[str, dict]:
    """runId -> {job, inputs, outputs, types, facet}."""
    out: dict[str, dict] = {}
    for event in ol_events:
        run = out.setdefault(
            event["run"]["runId"],
            {"job": event["job"], "inputs": set(), "outputs": set(), "types": [], "facet": None},
        )
        run["inputs"] |= {(d["namespace"], d["name"]) for d in event["inputs"]}
        run["outputs"] |= {(d["namespace"], d["name"]) for d in event["outputs"]}
        run["types"].append(event["eventType"])
        run["facet"] = event["run"].get("facets", {}).get("dcp", run["facet"])
    return out


def canonical(events) -> list[str]:
    return sorted(json.dumps(e, sort_keys=True) for e in events)


@pytest.fixture
def joining_consumer(ev):
    """Case 2: two producers (two traces) feed one consumer, which joins both
    traces and then writes once."""
    return [
        ev("ra", "read", ORDERS, "producer_a.py", pid=10, trace_id=TRACE_A, ts="2026-09-16T02:00:00Z"),
        ev("wa", "write", TOPIC, "producer_a.py", ["ra"], pid=10, trace_id=TRACE_A, ts="2026-09-16T02:00:01Z"),
        ev("rb", "read", REFUNDS, "producer_b.py", pid=11, trace_id=TRACE_B, ts="2026-09-16T02:00:02Z"),
        ev("wb", "write", TOPIC, "producer_b.py", ["rb"], pid=11, trace_id=TRACE_B, ts="2026-09-16T02:00:03Z"),
        ev("c1", "read", TOPIC, "consumer.py", ["wa"], pid=20, trace_id=TRACE_A, ts="2026-09-16T02:05:00Z"),
        ev("c2", "read", TOPIC, "consumer.py", ["wb"], pid=20, trace_id=TRACE_B, ts="2026-09-16T02:05:01Z"),
        ev("cw", "write", REVENUE, "consumer.py", ["c2"], pid=20, trace_id=TRACE_B, ts="2026-09-16T02:05:02Z"),
    ]  # fmt: skip


@pytest.fixture
def long_running(ev):
    """Case 3: one consumer process handling three traces, a write after each."""
    events = []
    for n, (trace, out) in enumerate(((TRACE_A, REVENUE), (TRACE_B, SUMMARY), (TRACE_C, REVENUE))):
        events += [
            ev(f"r{n}", "read", TOPIC, "loader.py", [f"w-up{n}"], pid=7, trace_id=trace,
               ts=f"2026-09-16T03:0{n}:00Z"),
            ev(f"w{n}", "write", out, "loader.py", [f"r{n}"], pid=7, trace_id=trace,
               ts=f"2026-09-16T03:0{n}:30Z"),
        ]  # fmt: skip
    return events


# --- A2 row 1 -------------------------------------------------------------------


def test_a2_01_one_process_one_trace_same_datasets_different_run_id(ev, validate):
    events = [
        ev("r", "read", ORDERS, ts="2026-09-16T02:00:00Z"),
        ev("w", "write", TOPIC, parent=["r"], ts="2026-09-16T02:00:05Z"),
    ]
    by_scope = {scope: to_openlineage(events, run_scope=scope) for scope in SCOPES}
    for ol in by_scope.values():
        validate(ol)
        assert [e["eventType"] for e in ol] == ["START", "COMPLETE"]
    old, new = by_scope["trace-process"], by_scope["process"]
    for a, b in zip(old, new, strict=True):
        assert (a["inputs"], a["outputs"], a["job"]) == (b["inputs"], b["outputs"], b["job"])
        assert (a["eventType"], a["eventTime"]) == (b["eventType"], b["eventTime"])
        assert a["run"]["runId"] != b["run"]["runId"]
    assert new[0]["run"]["runId"] == str(uuid.uuid5(DCP_RUN_NAMESPACE, "process|host-a|1|job.py"))
    assert old[0]["run"]["runId"] == str(
        uuid.uuid5(DCP_RUN_NAMESPACE, "11111111-1111-4111-8111-111111111111|host-a|1|job.py")
    )


# --- A2 row 2 -------------------------------------------------------------------


def test_a2_02_consumer_joining_two_traces_is_one_run(joining_consumer, validate):
    ol = to_openlineage(joining_consumer, run_scope="process")
    validate(ol)
    consumer = [r for r in runs(ol).values() if r["job"]["name"] == "consumer.py"]
    assert len(consumer) == 1
    (run,) = consumer
    assert run["inputs"] == {TOPIC}
    assert run["outputs"] == {REVENUE}
    assert run["facet"]["trace_ids"] == [TRACE_A, TRACE_B]
    assert run["facet"]["trace_id"] == TRACE_A
    assert len(runs(ol)) == 3  # two producers, one consumer


def test_a2_02_the_default_still_splits_the_joining_consumer(joining_consumer, validate):
    ol = to_openlineage(joining_consumer, run_scope="trace-process")
    validate(ol)
    consumer = [r for r in runs(ol).values() if r["job"]["name"] == "consumer.py"]
    assert len(consumer) == 2  # the P4 mapping: one run per (trace, process)
    assert sorted(sorted(r["outputs"]) for r in consumer) == [[], [REVENUE]]
    assert all("trace_ids" not in r["facet"] for r in consumer)


def test_a2_02_per_process_keeps_what_the_split_run_lost(joining_consumer):
    """The P5.1 recall loss: the default's implied edges lose topic -> revenue
    only when the write lands in the other trace's run; per process cannot."""
    implied = implied_dataset_edges(to_openlineage(joining_consumer, run_scope="process"))
    assert (TOPIC, REVENUE, "consumer.py") in implied
    assert dataset_provenance(implied, REVENUE) == {TOPIC, ORDERS, REFUNDS}


# --- A2 row 3 -------------------------------------------------------------------


def test_a2_03_long_running_consumer_is_one_run_with_every_input_and_output(long_running, validate):
    ol = to_openlineage(long_running, run_scope="process")
    validate(ol)
    (run,) = runs(ol).values()
    assert run["inputs"] == {TOPIC}
    assert run["outputs"] == {REVENUE, SUMMARY}
    assert run["types"] == ["START", "COMPLETE"]
    assert run["facet"]["trace_ids"] == [TRACE_A, TRACE_B, TRACE_C]
    assert len(run["facet"]["events"]) == 6
    assert [ol[0]["eventTime"], ol[1]["eventTime"]] == [
        "2026-09-16T03:00:00+00:00",
        "2026-09-16T03:02:30+00:00",
    ]
    assert len(runs(to_openlineage(long_running, run_scope="trace-process"))) == 3


# --- A2 rows 4 and 5 ------------------------------------------------------------


@pytest.mark.parametrize("scope", SCOPES)
def test_a2_04_reads_only_is_a_run_with_inputs_and_no_outputs(ev, validate, scope):
    ol = to_openlineage([ev("a", "read", ORDERS), ev("b", "read", REFUNDS)], run_scope=scope)
    validate(ol)
    (run,) = runs(ol).values()
    assert run["inputs"] == {ORDERS, REFUNDS}
    assert run["outputs"] == set()
    assert all(e["outputs"] == [] for e in ol)


@pytest.mark.parametrize("scope", SCOPES)
def test_a2_05_writes_only_is_a_run_with_outputs_and_no_inputs(ev, validate, scope):
    ol = to_openlineage([ev("a", "write", REVENUE), ev("b", "write", TOPIC)], run_scope=scope)
    validate(ol)
    (run,) = runs(ol).values()
    assert run["inputs"] == set()
    assert run["outputs"] == {REVENUE, TOPIC}


# --- A2 rows 6, 7 and 8 ---------------------------------------------------------


@pytest.mark.parametrize("scope", SCOPES)
def test_a2_06_same_job_on_two_hosts_is_two_runs_in_two_namespaces(ev, validate, scope):
    ol = to_openlineage(
        [ev("a", "read", ORDERS, host="h1"), ev("b", "read", ORDERS, host="h2")],
        run_scope=scope,
    )
    validate(ol)
    by_run = runs(ol)
    assert len(by_run) == 2
    assert {r["job"]["namespace"] for r in by_run.values()} == {"dcp://h1", "dcp://h2"}


@pytest.mark.parametrize("scope", SCOPES)
def test_a2_07_same_job_and_host_different_pids_is_two_runs(ev, validate, scope):
    ol = to_openlineage(
        [ev("a", "read", ORDERS, pid=100), ev("b", "write", REVENUE, pid=200)],
        run_scope=scope,
    )
    validate(ol)
    by_run = runs(ol)
    assert len(by_run) == 2
    assert sorted((sorted(r["inputs"]), sorted(r["outputs"])) for r in by_run.values()) == [
        ([], [REVENUE]),
        ([ORDERS], []),
    ]


def test_a2_08_pid_reuse_merges_two_processes_into_one_run(ev, validate):
    """The documented limitation (docs/decisions/openlineage-mapping.md): two
    processes with the same job name and pid on the same host, hours apart,
    are one run in `process` scope. DCP events carry no process start time."""
    first = [
        ev("r1", "read", ORDERS, "nightly.py", pid=4242, trace_id=TRACE_A, ts="2026-09-16T01:00:00Z"),
        ev("w1", "write", SUMMARY, "nightly.py", ["r1"], pid=4242, trace_id=TRACE_A, ts="2026-09-16T01:00:01Z"),
    ]  # fmt: skip
    second = [
        ev("r2", "read", REFUNDS, "nightly.py", pid=4242, trace_id=TRACE_B, ts="2026-09-16T05:00:00Z"),
        ev("w2", "write", REVENUE, "nightly.py", ["r2"], pid=4242, trace_id=TRACE_B, ts="2026-09-16T05:00:01Z"),
    ]  # fmt: skip
    ol = to_openlineage(first + second, run_scope="process")
    validate(ol)
    (run,) = runs(ol).values()  # merged: one run
    assert run["inputs"] == {ORDERS, REFUNDS}
    assert run["outputs"] == {SUMMARY, REVENUE}
    assert [e["eventTime"] for e in ol] == [
        "2026-09-16T01:00:00+00:00",
        "2026-09-16T05:00:01+00:00",
    ]
    # ... so the core model joins them: an edge neither process had.
    assert (ORDERS, REVENUE, "nightly.py") in implied_dataset_edges(ol)
    # The facet still carries each event's parents, so the DCP graph is exact.
    assert canonical(dcp_events(ol)) == canonical(first + second)
    # The default scope keeps them apart here only because their traces differ.
    assert len(runs(to_openlineage(first + second, run_scope="trace-process"))) == 2


# --- A2 rows 9, 10 and 11 -------------------------------------------------------


@pytest.mark.parametrize("scope", SCOPES)
def test_a2_09_no_events_no_openlineage_events(scope):
    assert to_openlineage([], run_scope=scope) == []


@pytest.mark.parametrize("scope", SCOPES)
def test_a2_10_every_permutation_translates_identically(joining_consumer, scope):
    events = joining_consumer[2:]  # 5 events, 120 orders
    reference = to_openlineage(events, run_scope=scope)
    for order in itertools.permutations(events):
        assert to_openlineage(list(order), run_scope=scope) == reference


@pytest.mark.parametrize("scope", SCOPES)
def test_a2_11_re_export_gives_identical_run_ids(joining_consumer, scope):
    first = to_openlineage(joining_consumer, run_scope=scope)
    again = to_openlineage([json.loads(json.dumps(e)) for e in joining_consumer], run_scope=scope)
    assert first == again
    assert [e["run"]["runId"] for e in first] == [e["run"]["runId"] for e in again]


def test_a2_11_the_two_scopes_never_share_a_run_id(joining_consumer, long_running):
    events = joining_consumer + long_running
    ids = {
        scope: {e["run"]["runId"] for e in to_openlineage(events, run_scope=scope)}
        for scope in SCOPES
    }
    assert ids["trace-process"].isdisjoint(ids["process"])


# --- A2 row 12 ------------------------------------------------------------------


@pytest.mark.parametrize("scope", SCOPES)
def test_a2_12_round_trip_gives_the_same_events_and_graph(joining_consumer, long_running, scope):
    graph = pytest.importorskip("app.graph")
    for events in (joining_consumer, long_running):
        ol = to_openlineage(events, run_scope=scope)
        assert canonical(dcp_events(ol)) == canonical(events)
        original, rebuilt = graph.build(events), graph.build(dcp_events(ol))
        assert rebuilt == original
        for ds in original.datasets():
            assert rebuilt.upstream(ds) == original.upstream(ds)


@pytest.mark.parametrize("scope", SCOPES)
def test_a2_12_round_trip_keeps_columns(ev, scope):
    event = ev("r", "read", ORDERS)
    event["columns"] = ["id", "total"]
    assert dcp_events(to_openlineage([event], run_scope=scope)) == [event]


# --- A2 row 13 ------------------------------------------------------------------


@pytest.mark.parametrize("scope", SCOPES)
def test_a2_13_every_event_and_facet_validates(joining_consumer, long_running, validate, scope):
    ol = to_openlineage(joining_consumer + long_running, run_scope=scope)
    validate(ol)
    facets = [e["run"]["facets"]["dcp"] for e in ol if e["eventType"] == "COMPLETE"]
    assert facets
    if scope == "process":
        assert all("trace_ids" in f for f in facets)
        assert all("trace_id" in entry for f in facets for entry in f["events"])
    else:  # backwards-compatible: the default's facets carry no new field
        assert all("trace_ids" not in f for f in facets)
        assert all("trace_id" not in entry for f in facets for entry in f["events"])


def test_a2_13_the_extended_facet_schema_still_accepts_a_p4_facet(validate, ev):
    """A facet written before P5.2 (no trace_ids) validates against the
    extended schema, and a trace_ids entry is checked when present."""
    jsonschema = pytest.importorskip("jsonschema")
    schema = pathlib.Path(__file__).parents[1] / "facets" / "DcpRunFacet.json"
    validator = jsonschema.Draft202012Validator(json.loads(schema.read_text()))
    p4 = to_openlineage([ev("r", "read", ORDERS)], run_scope="trace-process")[1]
    validator.validate(p4["run"]["facets"]["dcp"])
    extended = to_openlineage([ev("r", "read", ORDERS)], run_scope="process")[1]
    facet = extended["run"]["facets"]["dcp"]
    validator.validate(facet)
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(dict(facet, trace_ids=[]))


def test_a2_13_ground_truth_workloads_translate_to_valid_openlineage(harness, validate):
    for workload in harness.workloads():
        events = harness.replay(harness.load(workload))
        for scope in SCOPES:
            validate(to_openlineage(events, run_scope=scope))


# --- A2 row 14 ------------------------------------------------------------------


def _process_of(job: dict) -> tuple:
    return (job["namespace"], job["name"])


def assert_modes_agree(events) -> None:
    """Same datasets; per process, `process` outputs contain the union of the
    `trace-process` outputs (and likewise inputs)."""
    by_scope = {scope: to_openlineage(events, run_scope=scope) for scope in SCOPES}

    def datasets(ol):
        return {(d["namespace"], d["name"]) for e in ol for d in e["inputs"] + e["outputs"]}

    assert datasets(by_scope["process"]) == datasets(by_scope["trace-process"])
    union: dict = {}
    for run in runs(by_scope["trace-process"]).values():
        key = (_process_of(run["job"]), run["facet"]["job"].get("pid"))
        cell = union.setdefault(key, {"inputs": set(), "outputs": set()})
        cell["inputs"] |= run["inputs"]
        cell["outputs"] |= run["outputs"]
    per_process = {
        (_process_of(r["job"]), r["facet"]["job"].get("pid")): r
        for r in runs(by_scope["process"]).values()
    }
    assert set(per_process) == set(union)
    for key, cell in union.items():
        assert per_process[key]["outputs"] >= cell["outputs"]
        assert per_process[key]["inputs"] >= cell["inputs"]
    assert implied_dataset_edges(by_scope["process"]) >= implied_dataset_edges(
        by_scope["trace-process"]
    )


def test_a2_14_both_modes_over_the_same_events(joining_consumer, long_running):
    assert_modes_agree(joining_consumer)
    assert_modes_agree(long_running)
    assert_modes_agree(joining_consumer + long_running)


def test_a2_14_both_modes_over_real_capture_output(harness):
    """The hand-written keys (no process joins two traces: identical implied
    edges) and every generated scale key (where some do)."""
    for workload in harness.workloads():
        events = harness.replay(harness.load(workload))
        assert_modes_agree(events)
        assert implied_dataset_edges(
            to_openlineage(events, run_scope="process")
        ) == implied_dataset_edges(to_openlineage(events, run_scope="trace-process"))
    generated = harness.GROUND_TRUTH / "generated"
    for path in sorted(generated.glob("scale_*.json")):
        assert_modes_agree(harness.replay(json.loads(path.read_text(encoding="utf-8"))))


# --- The CLI --------------------------------------------------------------------


def test_cli_run_scope_process(tmp_path, joining_consumer, validate):
    source = tmp_path / "events.jsonl"
    source.write_text("".join(json.dumps(e) + "\n" for e in joining_consumer))
    out = tmp_path / "ol.jsonl"
    assert main(["--events", str(source), "--run-scope", "process", "--out", str(out)]) == 0
    written = [json.loads(line) for line in out.read_text().splitlines()]
    assert written == to_openlineage(joining_consumer, run_scope="process")
    validate(written)
    assert len(runs(written)) == 3


def test_cli_default_run_scope_is_unchanged(tmp_path, joining_consumer):
    source = tmp_path / "events.jsonl"
    source.write_text("".join(json.dumps(e) + "\n" for e in joining_consumer))
    default, explicit = tmp_path / "default.jsonl", tmp_path / "explicit.jsonl"
    assert main(["--events", str(source), "--out", str(default)]) == 0
    assert (
        main(["--events", str(source), "--run-scope", "trace-process", "--out", str(explicit)]) == 0
    )
    assert default.read_bytes() == explicit.read_bytes()
    assert [json.loads(x) for x in default.read_text().splitlines()] == to_openlineage(
        joining_consumer, run_scope="trace-process"
    )


def test_an_unknown_run_scope_is_refused(ev):
    with pytest.raises(ValueError, match="unknown run scope"):
        to_openlineage([ev("r", "read", ORDERS)], run_scope="trace")
