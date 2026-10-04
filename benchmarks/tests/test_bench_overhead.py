"""The overhead benchmark's fixed parts: tiers, configurations, workers. No infrastructure."""

import pathlib
import sys

import pytest
import sqlglot
from dcp.instrument import AUTOINSTRUMENT_DIR
from dcp.interceptors.postgres import _classify
from live import generate
from overhead import latency, queries
from sqlglot import exp

OVERHEAD = pathlib.Path(latency.__file__).parent


@pytest.mark.parametrize("tier", queries.TIERS, ids=[t.name for t in queries.TIERS])
def test_events_per_call_matches_capture(tier):
    reads, writes = _classify(tier.query)
    assert len(reads) + len(writes) == tier.events_per_call


def test_the_tiers_are_the_fixed_ones():
    by_name = {t.name: t for t in queries.TIERS}
    # P5's five, unchanged and first; P5.1 added the L tiers after them.
    assert list(by_name) == ["T1", "T2", "T3", "T4", "T5", "L1", "L3", "L5"]
    assert not any(by_name[n].literal for n in ("T1", "T2", "T3", "T4", "T5"))
    assert by_name["T1"].query == "SELECT id, total FROM orders WHERE id = %s"
    assert by_name["T3"].query == "INSERT INTO summary VALUES (%s, %s)"
    assert (
        by_name["T4"].query
        == "INSERT INTO summary SELECT id, total FROM orders WHERE id = %s"
    )
    assert _classify(by_name["T2"].query) == (["public.orders", "public.refunds"], [])
    assert _classify(by_name["T3"].query) == ([], ["public.summary"])


def test_t5_is_the_analytical_shape_the_task_asks_for():
    tree = sqlglot.parse_one(
        queries.T5_ANALYTICAL.replace("%s", "0"), dialect="postgres"
    )
    assert len(list(tree.find_all(exp.CTE))) >= 2
    assert list(tree.find_all(exp.Join))
    assert list(tree.find_all(exp.Window))
    assert list(tree.find_all(exp.AggFunc))
    assert 35 <= len(queries.T5_ANALYTICAL.splitlines()) <= 50
    assert _classify(queries.T5_ANALYTICAL) == (["public.orders", "public.refunds"], [])


PARAMETERISED = [t for t in queries.TIERS if not t.literal]
LITERAL = [t for t in queries.TIERS if t.literal]


@pytest.mark.parametrize("tier", PARAMETERISED, ids=[t.name for t in PARAMETERISED])
def test_params_match_the_placeholders(tier):
    assert len(tier.params(0)) == tier.query.count("%s")
    assert tier.statement(5) == (tier.query, tier.params(5))


@pytest.mark.parametrize("tier", LITERAL, ids=[t.name for t in LITERAL])
def test_literal_tiers_never_repeat_their_text(tier):
    texts = queries.literal_texts(tier, 12_000)
    assert len(set(texts)) == len(texts)
    assert all(
        "%s" not in text and tier.statement(n)[1] is None
        for n, text in enumerate(texts[:3])
    )


@pytest.mark.parametrize(
    ("literal", "twin"), [("L1", "T1"), ("L3", "T3"), ("L5", "T5")]
)
def test_literal_tiers_are_their_t_tier_with_literals_inlined(literal, twin):
    by_name = {t.name: t for t in queries.TIERS}
    text = by_name[literal].statement(1234)[0]
    assert _classify(text) == _classify(by_name[twin].query)
    assert by_name[literal].events_per_call == by_name[twin].events_per_call
    assert by_name[literal].returns_rows == by_name[twin].returns_rows
    assert "(added in P5.1)" in by_name[literal].label
    if literal == "L5":  # one numeric literal, and only that, differs from T5
        assert text == queries.T5_ANALYTICAL.replace("%s", "-1234")


@pytest.mark.parametrize("worker", ["pg_worker.py", "kafka_worker.py", "queries.py"])
def test_the_timed_programs_contain_no_dcp_code(worker):
    """The same program runs in every configuration; only the environment differs."""
    source = (OVERHEAD / worker).read_text(encoding="utf-8")
    assert generate.dcp_code_in(source) == []


def test_the_backpressure_worker_is_the_one_dcp_aware_program():
    source = (OVERHEAD / "backpressure_worker.py").read_text(encoding="utf-8")
    assert generate.dcp_code_in(source)


def test_configurations_and_order_are_fixed():
    # P5's configurations, in P5's order; P5.1's ablations after them.
    assert latency.CONFIGS == (
        "base", "file", "http", "http-down", "file+sqlcomment", "wrap-only", "capture-null",
    )  # fmt: skip
    assert latency.KAFKA_CONFIGS == (
        "base",
        "file",
        "http",
        "wrap-only",
        "capture-null",
    )
    assert latency.ADDED_IN_P51 == ("wrap-only", "capture-null")
    assert latency.PROFILE_TIERS == ("T1", "L1")
    assert (latency.FULL.rounds, latency.FULL.calls, latency.FULL.warmup) == (
        10,
        2000,
        200,
    )
    assert (latency.QUICK.rounds, latency.QUICK.calls, latency.QUICK.warmup) == (
        5,
        300,
        50,
    )
    assert (latency.FULL.kafka_messages, latency.QUICK.kafka_messages) == (
        10_000,
        2_000,
    )


def test_base_runs_without_dcp(tmp_path, monkeypatch):
    monkeypatch.setenv("DCP_EMIT", "file://leak.jsonl")
    env = latency.config_env("base", tmp_path / "s.jsonl", "http://b", "http://c")
    assert not [k for k in env if k.startswith("DCP_")]
    assert AUTOINSTRUMENT_DIR not in env.get("PYTHONPATH", "")
    assert latency.command("base", latency.PG_WORKER, "out", 1, 2) == [
        sys.executable, str(latency.PG_WORKER), "out", "1", "2",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("config", "emit", "propagate"),
    [
        ("file", "file://{sink}", None),
        ("http", "http://backend", None),
        ("http-down", "http://closed", None),
        ("file+sqlcomment", "file://{sink}", "1"),
        ("wrap-only", "null://", None),
        ("capture-null", "null://", None),
    ],
)
def test_instrumented_configurations(tmp_path, config, emit, propagate):
    sink = tmp_path / "s.jsonl"
    env = latency.config_env(config, sink, "http://backend", "http://closed")
    assert env["DCP_EMIT"] == emit.format(sink=sink)
    assert env.get("DCP_PROPAGATE_SQL") == propagate
    assert env.get("DCP_CAPTURE") == ("off" if config == "wrap-only" else None)
    cmd = latency.command(config, latency.PG_WORKER, "out")
    assert cmd[:3] == [sys.executable, "-m", "dcp.instrument"]
    assert cmd[3:] == [sys.executable, str(latency.PG_WORKER), "out"]


def test_the_closed_port_refuses_connections():
    import socket

    reserved = latency.reserve_closed_port()
    try:
        with pytest.raises(OSError):
            socket.create_connection(
                ("127.0.0.1", reserved.getsockname()[1]), timeout=3
            )
    finally:
        reserved.close()


def rounds(**p50s):
    """Per-round stats for configs: p50 as given, throughput from a fixed per-call cost."""
    return {
        config: [{"p50_us": v, "p99_us": v, "per_s": 1e6 / (100 + v)} for v in values]
        for config, values in p50s.items()
    }


def test_attribution_splits_the_added_cost_by_component():
    r = rounds(
        base=[100, 102, 98],
        **{"wrap-only": [101, 103, 99], "capture-null": [111, 113, 109]},
        **{"http-down": [116, 118, 114], "file": [146, 148, 144]},
        **{"file+sqlcomment": [168, 170, 166]},
    )
    parts = {row["component"]: row for row in latency.attribution(r)}
    expected = {"wrapper": 1, "capture + construction": 10, "async enqueue": 5,
                "synchronous file write": 30, "SQL comment": 22}  # fmt: skip
    assert list(parts) == list(expected)
    for name, value in expected.items():
        assert parts[name]["p50_us"]["estimate"] == pytest.approx(value)
        assert parts[name]["implied_us"]["estimate"] == pytest.approx(value)
    assert parts["wrapper"]["measured_as"] == "wrap-only"
    assert parts["SQL comment"]["measured_as"] == "file+sqlcomment − file"


def test_attribution_skips_components_whose_configs_did_not_run():
    r = rounds(base=[1.0, 2.0], **{"wrap-only": [2.0, 3.0]})
    assert [row["component"] for row in latency.attribution(r)] == ["wrapper"]


def test_compare_reports_the_implied_cost_per_call():
    r = rounds(base=[100, 100, 100], file=[130, 132, 128])
    v = latency._compare(r, ("base", "file"), "per_s")["file"]
    # per_s = 1e6 / (100 + p50): the implied cost is exactly the p50 difference
    assert v["implied_added_us"]["estimate"] == pytest.approx(30)
    assert v["added_p50_us"]["estimate"] == pytest.approx(30)
