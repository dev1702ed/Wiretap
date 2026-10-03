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
    assert list(by_name) == ["T1", "T2", "T3", "T4", "T5"]
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


@pytest.mark.parametrize("tier", queries.TIERS, ids=[t.name for t in queries.TIERS])
def test_params_match_the_placeholders(tier):
    assert len(tier.params(0)) == tier.query.count("%s")


@pytest.mark.parametrize("worker", ["pg_worker.py", "kafka_worker.py", "queries.py"])
def test_the_timed_programs_contain_no_dcp_code(worker):
    """The same program runs in every configuration; only the environment differs."""
    source = (OVERHEAD / worker).read_text(encoding="utf-8")
    assert generate.dcp_code_in(source) == []


def test_the_backpressure_worker_is_the_one_dcp_aware_program():
    source = (OVERHEAD / "backpressure_worker.py").read_text(encoding="utf-8")
    assert generate.dcp_code_in(source)


def test_configurations_and_order_are_fixed():
    assert latency.CONFIGS == ("base", "file", "http", "http-down", "file+sqlcomment")
    assert latency.KAFKA_CONFIGS == ("base", "file", "http")
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
    ],
)
def test_instrumented_configurations(tmp_path, config, emit, propagate):
    sink = tmp_path / "s.jsonl"
    env = latency.config_env(config, sink, "http://backend", "http://closed")
    assert env["DCP_EMIT"] == emit.format(sink=sink)
    assert env.get("DCP_PROPAGATE_SQL") == propagate
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
