"""Seeding, the live harness's environment, and the pluggable event source."""

import os
import pathlib

import sqlglot
from dcp.instrument import AUTOINSTRUMENT_DIR
from harness import datasets, load, replay, workloads
from live import generate, run_live, seed
from score import REPLAY_INTRO, report_lines, score_all

# The schema the task fixes for every table the keys use.
COLUMNS = {
    "orders": "id int, total numeric",
    "refunds": "id int, amount numeric",
    "summary": "id int, total numeric",
    "refund_summary": "id int, amount numeric",
    "daily_revenue": "id int, total numeric",
}


def key_tables() -> set[str]:
    tables = set()
    for name in workloads():
        for namespace, dataset in datasets(load(name)).values():
            if namespace.startswith("postgres://"):
                tables.add(dataset.rsplit(".", 1)[-1])
    return tables


def test_every_key_table_is_created_with_its_columns():
    assert set(seed.TABLES) == key_tables() == set(COLUMNS)
    assert seed.TABLES == COLUMNS
    statements = seed.seed_sql()
    for table, columns in COLUMNS.items():
        assert f"CREATE TABLE {table} ({columns})" in statements


def test_seeding_drops_first_and_only_fills_sources():
    statements = seed.seed_sql()
    assert statements[0] == "DROP TABLE IF EXISTS " + ", ".join(COLUMNS)
    inserts = [s for s in statements if s.startswith("INSERT")]
    assert [s.split()[2] for s in inserts] == ["orders", "refunds"]
    assert all(seed.ROWS[t] for t in ("orders", "refunds"))


def test_seeding_sql_is_valid_postgres():
    for statement in seed.seed_sql():
        assert sqlglot.parse_one(statement, dialect="postgres") is not None


def test_seed_targets_the_keys_addresses_and_topic():
    assert seed.PG_CONNINFO == generate.PG_CONNINFO
    assert seed.KAFKA_BOOTSTRAP == generate.KAFKA_BOOTSTRAP
    namespaces = {ns for name in workloads() for ns, _ in datasets(load(name)).values()}
    assert namespaces == {"postgres://localhost:5432", "kafka://localhost:9092"}
    topics = {
        step[k]
        for name in workloads()
        for p in load(name)["processes"]
        for step in p["steps"]
        for k in ("produce", "consume")
        if k in step
    }
    assert topics == {seed.TOPIC}


def test_seed_contains_no_dcp_code():
    source = pathlib.Path(seed.__file__).read_text(encoding="utf-8")
    assert generate.dcp_code_in(source) == []


def test_clean_env_strips_dcp(monkeypatch):
    monkeypatch.setenv("DCP_EMIT", "file://x.jsonl")
    monkeypatch.setenv("DCP_JOB_NAME", "leak")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join([AUTOINSTRUMENT_DIR, "keep"]))
    monkeypatch.setenv("DCP_PG_PASSWORD", "s3cret")
    env = run_live.clean_env()
    assert not [k for k in env if k.startswith("DCP_")]
    assert env["PYTHONPATH"] == "keep"
    assert env["PGPASSWORD"] == "s3cret"


def test_unreachable_services_are_reported(monkeypatch):
    monkeypatch.setattr(run_live, "LIBRARIES", ())
    monkeypatch.setattr(run_live, "ADDRESSES", {"PostgreSQL": ("127.0.0.1", 9)})
    reason = run_live.unavailable()
    assert reason.startswith("PostgreSQL is not reachable at 127.0.0.1:9")


def test_missing_libraries_are_reported(monkeypatch):
    monkeypatch.setattr(run_live, "LIBRARIES", ("dcp_no_such_library",))
    assert "missing dcp_no_such_library" in run_live.unavailable()


def test_the_event_source_is_pluggable():
    seen = []

    def source(key):
        seen.append(key["workload"])
        return replay(key)

    assert score_all(source) == score_all(replay)
    assert seen == workloads()


def test_replay_report_matches_the_pinned_output():
    """The same pin as backend/tests/test_backend_score.py, without a subprocess."""
    pinned = (
        pathlib.Path(__file__).parents[2]
        / "backend"
        / "tests"
        / "data"
        / "score_replay.txt"
    )
    lines = report_lines(score_all(replay), REPLAY_INTRO)
    assert "\n".join(lines) + "\n" == pinned.read_bytes().decode("utf-8")
