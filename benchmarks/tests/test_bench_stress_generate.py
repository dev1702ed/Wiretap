"""The generator's P5.2 job kinds (B1): multi-record consumers and store-mediated
reads, the stress set, and default-off byte identity.

Every row of the case matrix in docs/tasks/P5.2.md (B2) has a test here, named
`test_b2_<row>_...`. Rows 1-5 use HAND-WRITTEN expected truth, worked out
below from each plan's programs, on tiny hand-made plans: never truth computed
by the generator itself.
"""

import json
import os

import generate
import pytest
from harness import replay
from live import generate as programs

# The stress set B3 asks for, named here so that each test below runs (and,
# on a generator without it, fails) on its own.
STRESS_NAMES = ["stress_large", "stress_s01", "stress_s02", "stress_s03", "stress_s04",
                "stress_s05"]  # fmt: skip

# --- Hand-made plans -----------------------------------------------------------

S1, S2, S3, S4 = "gen_src_01", "gen_src_02", "gen_src_03", "gen_src_04"
T1 = "gen_topic_01"
O1, O2, O3, O4 = (f"gen_out_00{i}" for i in range(1, 5))

# Multi-record consumers (rows 1 and 2).
#   p1.py reads S1 (10 + 20 = 30), produces r001=30 to T1
#   p2.py reads S2 (5), produces r002=5 to T1
#   p3.py reads S3 (1) and S4 (a distractor), uses S3 only: produces r003=1 to T1
#   c2.py consumes r001 then r002 from T1 (two producers, two traces): writes 35 to O1
#   c3.py consumes r002, r003, r001 from T1 (three producers): writes 36 to O2
MULTI_PLAN = {
    "rows": {S1: [[1, 10], [2, 20]], S2: [[1, 5]], S3: [[1, 1]], S4: [[1, 100]]},
    "jobs": [
        {"kind": "script", "job": "p1.py", "reads": [S1], "used": [S1],
         "outputs": [["produce", T1, "r001"]]},
        {"kind": "script", "job": "p2.py", "reads": [S2], "used": [S2],
         "outputs": [["produce", T1, "r002"]]},
        {"kind": "script", "job": "p3.py", "reads": [S4, S3], "used": [S3],
         "outputs": [["produce", T1, "r003"]]},
        {"kind": "consumer", "job": "c2.py",
         "steps": [["consume", T1, "r001"], ["consume", T1, "r002"]], "out": O1},
        {"kind": "consumer", "job": "c3.py",
         "steps": [["consume", T1, "r002"], ["consume", T1, "r003"], ["consume", T1, "r001"]],
         "out": O2},
    ],
}  # fmt: skip

# Store-mediated reads (rows 3, 4 and 5).
#   m.py:  INSERT INTO O1 SELECT a.id, a.v + b.v FROM S1 a JOIN S2 b ON id: ids 1 only,
#          so O1 holds (1, 10 + 5) = (1, 15)
#   a.py:  reads O1 (store-mediated, chain 1): writes 15 to O2
#   b.py:  reads O2 (written by a store-read job: chain 2): writes 15 to O3
#   d.py:  reads S3 (a distractor) and O1 (store-mediated): writes 15 to O4
STORE_PLAN = {
    "rows": {S1: [[1, 10], [2, 20]], S2: [[1, 5]], S3: [[1, 7]]},
    "jobs": [
        {"kind": "multi", "job": "m.py", "steps": [["insert_select", O1, [S1, S2]]]},
        {"kind": "store", "job": "a.py", "reads": [O1], "used": [O1], "out": O2},
        {"kind": "store", "job": "b.py", "reads": [O2], "used": [O2], "out": O3},
        {"kind": "store", "job": "d.py", "reads": [S3, O1], "used": [O1], "out": O4},
    ],
}  # fmt: skip


@pytest.fixture(scope="module")
def multi_key():
    return generate.derive("hand_multi", MULTI_PLAN, {"seed": None})


@pytest.fixture(scope="module")
def store_key():
    return generate.derive("hand_store", STORE_PLAN, {"seed": None})


def steps_of(key):
    return {p["job"]: p["steps"] for p in key["processes"]}


def provenance(key):
    return {p["dataset"]: set(p["upstream"]) for p in key["provenance"]}


def edges(key):
    return {(e["from"], e["to"], e["job"]) for e in key["dataset_edges"]}


def dcp_upstream(key, dataset):
    """What DCP's run-level provenance finds, from its real capture code."""
    from app.graph import build

    ds = {a: (d["namespace"], d["name"]) for a, d in key["datasets"].items()}
    alias = {v: k for k, v in ds.items()}
    return {alias[d] for d in build(replay(key)).upstream(ds[dataset])}


# --- Row 1 ---------------------------------------------------------------------


def test_b2_01_multi_record_consumer_two_records_two_producers(multi_key):
    assert steps_of(multi_key)["c2.py"] == [
        {"consume": T1, "record": "r001=30"},
        {"consume": T1, "record": "r002=5"},
        {"sql": f"INSERT INTO {O1} VALUES (1, 35)"},
    ]
    assert provenance(multi_key)[O1] == {T1, S1, S2}  # both producers' inputs
    assert (T1, O1, "c2.py") in edges(multi_key)
    runs = {(e["from_job"], e["to_job"], e["via"]) for e in multi_key["run_edges"]}
    assert {("p1.py", "c2.py", T1), ("p2.py", "c2.py", T1)} <= runs
    assert multi_key["generated"]["multi_record"]["c2.py"] == ["r001=30", "r002=5"]
    pytest.importorskip("app.graph")
    # The failure mode, measured: job-level parenting keeps the latest read of
    # T1 (r002, from p2.py), so p1.py's input S1 is lost.
    assert dcp_upstream(multi_key, O1) == {T1, S2}


# --- Row 2 ---------------------------------------------------------------------


def test_b2_02_three_records_one_producer_with_a_distractor(multi_key):
    assert steps_of(multi_key)["c3.py"][-1] == {
        "sql": f"INSERT INTO {O2} VALUES (1, 36)"
    }
    assert provenance(multi_key)[O2] == {T1, S1, S2, S3}  # S4 is p3.py's distractor
    assert S4 not in provenance(multi_key)[O2]
    assert provenance(multi_key)[T1] == {S1, S2, S3}
    assert multi_key["generated"]["distractors"] == {"p3.py": [S4]}
    assert multi_key["generated"]["multi_record"]["c3.py"] == [
        "r002=5",
        "r003=1",
        "r001=30",
    ]
    runs = {(e["from_job"], e["to_job"], e["via"]) for e in multi_key["run_edges"]}
    assert {
        ("p1.py", "c3.py", T1),
        ("p2.py", "c3.py", T1),
        ("p3.py", "c3.py", T1),
    } <= runs
    pytest.importorskip("app.graph")
    assert dcp_upstream(multi_key, O2) == {T1, S1}  # the last record is p1.py's


# --- Rows 3, 4 and 5 -----------------------------------------------------------


def test_b2_03_store_chain_of_length_one_crosses_the_table(store_key):
    assert steps_of(store_key)["a.py"] == [
        {"sql": f"SELECT id, v FROM {O1}"},
        {"sql": f"INSERT INTO {O2} VALUES (1, 15)"},
    ]
    assert provenance(store_key)[O1] == {S1, S2}
    assert provenance(store_key)[O2] == {
        O1,
        S1,
        S2,
    }  # through the table to m.py's inputs
    assert (O1, O2, "a.py") in edges(store_key)
    assert store_key["generated"]["store_reads"]["a.py"] == [O1]
    assert store_key["tables"][O1]["rows"] == []  # only the source tables are seeded


def test_b2_04_store_chain_of_length_two_is_transitive(store_key):
    assert steps_of(store_key)["b.py"] == [
        {"sql": f"SELECT id, v FROM {O2}"},
        {"sql": f"INSERT INTO {O3} VALUES (1, 15)"},
    ]
    assert provenance(store_key)[O3] == {O2, O1, S1, S2}
    assert edges(store_key) >= {(O1, O2, "a.py"), (O2, O3, "b.py")}


def test_b2_05_store_read_with_a_distractor(store_key):
    assert steps_of(store_key)["d.py"] == [
        {"sql": f"SELECT id, v FROM {S3}"},
        {"sql": f"SELECT id, v FROM {O1}"},
        {"sql": f"INSERT INTO {O4} VALUES (1, 15)"},
    ]
    assert provenance(store_key)[O4] == {O1, S1, S2}  # S3 excluded, O1 included
    assert (S3, O4, "d.py") not in edges(store_key)
    assert store_key["generated"]["distractors"] == {"d.py": [S3]}
    assert store_key["generated"]["store_reads"] == {
        "a.py": [O1],
        "b.py": [O2],
        "d.py": [O1],
    }


def test_b2_03_to_05_dcp_stops_at_the_table(store_key):
    pytest.importorskip("app.graph")
    assert dcp_upstream(store_key, O2) == {O1}
    assert dcp_upstream(store_key, O3) == {O2}
    assert dcp_upstream(store_key, O4) == {O1, S3}  # and the distractor, job-level


def test_the_complete_hand_truth(multi_key, store_key):
    assert edges(multi_key) == {
        (S1, T1, "p1.py"), (S2, T1, "p2.py"), (S3, T1, "p3.py"),
        (T1, O1, "c2.py"), (T1, O2, "c3.py"),
    }  # fmt: skip
    assert edges(store_key) == {
        (S1, O1, "m.py"), (S2, O1, "m.py"), (O1, O2, "a.py"), (O2, O3, "b.py"),
        (O1, O4, "d.py"),
    }  # fmt: skip
    assert provenance(store_key) == {
        O1: {S1, S2}, O2: {O1, S1, S2}, O3: {O2, O1, S1, S2}, O4: {O1, S1, S2},
    }  # fmt: skip


# --- Row 6 ---------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(generate.KEYS))
def test_b2_06_both_parameters_off_regenerates_every_committed_key(name):
    seed, overrides = generate.KEYS[name]
    committed = generate.path_for(name).read_bytes()
    default = generate.dumps(generate.generate(name, seed, **overrides))
    explicit = generate.dumps(
        generate.generate(name, seed, p_multi_record=0.0, p_store_read=0.0, **overrides)
    )
    assert default.encode("utf-8") == committed
    assert explicit.encode("utf-8") == committed
    key = json.loads(committed)
    assert key["generated"]["version"] == "1.0"
    assert (
        "store_reads" not in key["generated"] and "multi_record" not in key["generated"]
    )


def test_b2_06_the_generator_is_version_1_1_and_stress_keys_record_it():
    assert generate.GENERATOR_VERSION == "1.1"
    assert generate.VERSION == "1.0"  # what a key with both parameters off records
    assert generate.STRESS_DEFAULTS == {"p_multi_record": 0.0, "p_store_read": 0.0}
    for name in generate.STRESS_KEYS:
        g = generate.load_generated(name)["generated"]
        assert g["version"] == "1.1"
        assert g["parameters"]["p_multi_record"] == 0.15
        assert g["parameters"]["p_store_read"] == 0.25


# --- Row 7 ---------------------------------------------------------------------


@pytest.mark.parametrize("name", STRESS_NAMES)
def test_b2_07_same_seed_and_parameters_give_identical_bytes(name):
    seed, overrides = generate.STRESS_KEYS[name]
    first = generate.dumps(generate.generate(name, seed, **overrides))
    again = generate.dumps(generate.generate(name, seed, **overrides))
    assert first == again
    assert generate.path_for(name).read_bytes() == first.encode("utf-8")


def test_b2_07_the_stress_set_is_exactly_the_configured_keys():
    assert generate.stress_names() == sorted(generate.STRESS_KEYS)
    assert sorted(generate.STRESS_KEYS) == STRESS_NAMES
    for name in generate.STRESS_KEYS:
        jobs = len(generate.load_generated(name)["processes"])
        assert jobs == (100 if name == "stress_large" else 30), name
        assert generate.path_for(name).parent.name == "stress"
    assert not set(generate.generated_names()) & set(generate.STRESS_KEYS)


# --- Row 8 ---------------------------------------------------------------------


@pytest.mark.parametrize("name", STRESS_NAMES)
def test_b2_08_stress_programs_contain_no_dcp_code(name):
    key = generate.load_generated(name)
    for index, process in enumerate(key["processes"]):
        group = programs.group_id("run", name, index)
        if process["kind"] == "notebook":
            source = programs.notebook_source(programs.notebook(name, process, group))
        else:
            source = programs.script_source(name, process, group)
        assert programs.dcp_code_in(source) == [], process["job"]


# --- Row 9 ---------------------------------------------------------------------


def writes_of(process) -> set[str]:
    return {
        s["sql"].split()[2]
        for s in process["steps"]
        if s.get("sql", "").startswith("INSERT")
    }


def reads_of(process) -> list[str]:
    return [
        s["sql"].split()[-1]
        for s in process["steps"]
        if s.get("sql", "").startswith("SELECT")
    ]


@pytest.mark.parametrize("name", STRESS_NAMES)
def test_b2_09_every_store_read_comes_after_its_producing_write(name):
    """Checked on the key's own programs: the process that reads a written
    table runs after the process whose INSERT wrote it, and the written table
    is never seeded."""
    key = generate.load_generated(name)
    written_by = {}
    for index, process in enumerate(key["processes"]):
        for table in reads_of(process):
            if table in key["tables"] and not key["tables"][table]["rows"]:
                assert table in written_by, (name, process["job"], table)
                assert written_by[table] < index
        for table in writes_of(process):
            assert table not in written_by, "a table is written once"
            written_by[table] = index
    store_reads = key["generated"]["store_reads"]
    assert store_reads
    jobs = [p["job"] for p in key["processes"]]
    for job, (table,) in store_reads.items():
        assert written_by[table] < jobs.index(job)


@pytest.mark.parametrize("name", STRESS_NAMES)
def test_b2_09_chains_are_at_most_two_and_multi_records_span_producers(name):
    key = generate.load_generated(name)
    g = key["generated"]
    writer = {e["to"]: e["job"] for e in key["dataset_edges"]}
    for (table,) in g["store_reads"].values():
        upstream_job = writer[table]
        if upstream_job in g["store_reads"]:
            (second,) = g["store_reads"][upstream_job]
            assert writer[second] not in g["store_reads"], "chain longer than 2"
    producer = {}
    for p in key["processes"]:
        for s in p["steps"]:
            if "produce" in s:
                producer[s["record"]] = (p["job"], s["produce"])
    for records in g["multi_record"].values():
        assert 2 <= len(records) <= 3
        assert len({producer[r][1] for r in records}) == 1  # one topic
        assert len({producer[r][0] for r in records}) == len(
            records
        )  # distinct producers


# --- Row 10 --------------------------------------------------------------------

LIVE = os.environ.get("DCP_TEST_LIVE") == "1"


def tiny_stress_key() -> dict:
    """8 jobs with both kinds forced on: small enough for a unit-test live run."""
    return generate.generate(
        "stress_tiny", 7, jobs=8, p_multi_record=1.0, p_store_read=0.5
    )


def test_b2_10_the_tiny_stress_key_has_both_kinds():
    g = tiny_stress_key()["generated"]
    assert g["store_reads"] and g["multi_record"]


@pytest.mark.skipif(
    not LIVE,
    reason="live: set DCP_TEST_LIVE=1 with Postgres and Kafka on localhost "
    "(DESTRUCTIVE: drops and re-creates gen_* tables and topics)",
)
def test_b2_10_live_replay_of_a_tiny_stress_key(tmp_path):
    from live import run_live
    from score import score_workload

    reason = run_live.unavailable()
    assert reason is None, reason
    key = tiny_stress_key()
    path = tmp_path / "stress_tiny.json"
    path.write_text(generate.dumps(key), encoding="utf-8")
    record, events = run_live.run_workload(key, tmp_path / "run", "unit", key_path=path)
    assert [p["exit_code"] for p in record["processes"]] == [0] * len(key["processes"])
    live, replayed = score_workload(key, events), score_workload(key, replay(key))
    for section in ("dcp", "openlineage", "openlineage_per_process"):
        assert [
            (r["label"], r["hits"], r["found"], r["expected"]) for r in live[section]
        ] == [
            (r["label"], r["hits"], r["found"], r["expected"])
            for r in replayed[section]
        ]
