"""The workload generator (P5.1, B2): reproducible, truthful, and free of DCP.

The truth-derivation tests below were worked out BY HAND from each plan's
programs: which rows each job reads, which values it computes, and so which
inputs every written dataset really came from. They are not derived by
calling the code under test.
"""

import ast
import json
import pathlib
import subprocess
import sys

import generate
import pytest
from harness import replay
from live import generate as programs
from score import score_workload

GROUND_TRUTH = pathlib.Path(generate.__file__).resolve().parent

# A hand-made plan exercising every job kind (tables named as the generator names them).
S1, S2, S3 = "gen_src_01", "gen_src_02", "gen_src_03"
T1 = "gen_topic_01"
O1, O2, O3, O4, O5 = (f"gen_out_00{i}" for i in range(1, 6))
PLAN = {
    "rows": {S1: [[1, 10], [2, 20]], S2: [[1, 5]], S3: [[1, 1]]},
    "jobs": [
        # reads S1 and S3, uses only S1 (S3 is a distractor): sum 10 + 20 = 30
        {"kind": "script", "job": "a.py", "reads": [S1, S3], "used": [S1],
         "outputs": [["produce", T1, "r001"], ["insert", O1]]},
        # a second producer on T1 (fan-in): sum 5
        {"kind": "script", "job": "b.py", "reads": [S2], "used": [S2],
         "outputs": [["produce", T1, "r002"]]},
        # consumes a.py's record (30), reads S2 as a distractor, writes 30
        {"kind": "consumer", "job": "c.py", "steps": [["consume", T1, "r001"], ["read", S2]],
         "out": O2},
        # two INSERT ... SELECT statements around a distractor read of S3
        {"kind": "multi", "job": "m.py",
         "steps": [["insert_select", O3, [S1, S2]], ["read", S3], ["insert_select", O4, [S2]]]},
        # uses both reads: 1 + 10 + 20 = 31
        {"kind": "notebook", "job": "n.ipynb", "reads": [S3, S1], "used": [S3, S1],
         "outputs": [["insert", O5]]},
    ],
}  # fmt: skip


@pytest.fixture(scope="module")
def key():
    return generate.derive("hand", PLAN, {"seed": None})


def test_the_programs_are_exactly_the_planned_steps(key):
    steps = {p["job"]: p["steps"] for p in key["processes"]}
    assert steps["a.py"] == [
        {"sql": f"SELECT id, v FROM {S1}"},
        {"sql": f"SELECT id, v FROM {S3}"},
        {"produce": T1, "record": "r001=30"},
        {"sql": f"INSERT INTO {O1} VALUES (1, 30)"},
    ]
    assert steps["b.py"] == [
        {"sql": f"SELECT id, v FROM {S2}"},
        {"produce": T1, "record": "r002=5"},
    ]
    assert steps["c.py"] == [
        {"consume": T1, "record": "r001=30"},
        {"sql": f"SELECT id, v FROM {S2}"},
        {"sql": f"INSERT INTO {O2} VALUES (1, 30)"},
    ]
    assert steps["m.py"] == [
        {
            "sql": f"INSERT INTO {O3} SELECT a.id, a.v + b.v FROM {S1} AS a JOIN {S2} AS b ON b.id = a.id"
        },
        {"sql": f"SELECT id, v FROM {S3}"},
        {"sql": f"INSERT INTO {O4} SELECT id, v FROM {S2}"},
    ]
    assert steps["n.ipynb"] == [
        {"sql": f"SELECT id, v FROM {S3}"},
        {"sql": f"SELECT id, v FROM {S1}"},
        {"sql": f"INSERT INTO {O5} VALUES (1, 31)"},
    ]
    kinds = {p["job"]: p["kind"] for p in key["processes"]}
    assert kinds == {"a.py": "script", "b.py": "script", "c.py": "script", "m.py": "script",
                     "n.ipynb": "notebook"}  # fmt: skip


def test_the_truth_credits_only_real_data_flow(key):
    edges = {(e["from"], e["to"], e["job"]) for e in key["dataset_edges"]}
    assert edges == {
        (S1, T1, "a.py"), (S1, O1, "a.py"), (S2, T1, "b.py"), (T1, O2, "c.py"),
        (S1, O3, "m.py"), (S2, O3, "m.py"), (S2, O4, "m.py"), (S3, O5, "n.ipynb"),
        (S1, O5, "n.ipynb"),
    }  # fmt: skip
    assert key["run_edges"] == [{"from_job": "a.py", "to_job": "c.py", "via": T1}]
    provenance = {p["dataset"]: set(p["upstream"]) for p in key["provenance"]}
    assert provenance == {
        O1: {S1}, O2: {T1, S1}, O3: {S1, S2}, O4: {S2}, O5: {S1, S3}, T1: {S1, S2},
    }  # fmt: skip
    assert set(key["datasets"]) == {S1, S2, S3, T1, O1, O2, O3, O4, O5}
    assert key["datasets"][S1] == {
        "namespace": "postgres://localhost:5432",
        "name": f"dcp.public.{S1}",
    }
    assert key["datasets"][T1] == {"namespace": "kafka://localhost:9092", "name": T1}
    assert key["generated"]["distractors"] == {"a.py": [S3], "c.py": [S2], "m.py": [S3]}
    assert key["tables"][S1] == {"columns": "id int, v int", "rows": [[1, 10], [2, 20]]}
    assert key["tables"][O1]["rows"] == [] and key["topics"] == [T1]


def test_dcp_over_approximates_exactly_where_the_hand_analysis_says(key):
    """Replayed through DCP's real capture code: precise where SQL names its
    sources, job-level after a distractor, and recall 1.0 everywhere."""
    rows = {r["label"]: r for r in score_workload(key, replay(key))["dcp"]}

    def hfe(label):
        return rows[label]["hits"], rows[label]["found"], rows[label]["expected"]

    assert hfe(f"upstream({O1}) run-level") == (1, 2, 1)  # + the distractor S3
    assert hfe(f"upstream({O2}) run-level") == (2, 4, 2)  # + S2 (own) and S3 (a.py's)
    assert hfe(f"upstream({O3}) run-level") == (2, 2, 2)  # INSERT ... SELECT: precise
    assert hfe(f"upstream({O4}) run-level") == (1, 1, 1)
    assert hfe(f"upstream({O5}) run-level") == (2, 2, 2)  # every read was used
    assert hfe(f"upstream({T1}) run-level") == (2, 3, 2)  # + S3, through a.py
    assert hfe("run edges") == (1, 1, 1)
    assert hfe("nodes") == (9, 9, 9)
    assert all(r["hits"] == r["expected"] for r in rows.values())  # recall 1.0


# Tiny SEEDED workloads (4 jobs each), read job by job and checked by hand:
# the rows, which reads each job uses, the sums it writes, and so the truth.
#
# seed 1: gen_src_03 rows 64, 98, 58 (sum 220); gen_src_04 61, 84, 49 (194);
#   gen_src_02 9, 33, 16 (58).
#   gen_job_001.py (multi): out_001 <- src_04; out_002 <- src_01 JOIN src_03;
#                           out_003 <- src_03 JOIN src_04
#   gen_nb_002.ipynb: reads src_01 (distractor) and src_03; writes 220 to out_004
#   gen_job_003.py: reads src_04 and src_02, uses both (194 + 58 = 252); produces
#                   r001=252 to topic_02 and r002=252 to topic_01; writes 252 to out_005
#   gen_job_004.py: consumes r002=252 from topic_01; writes 252 to out_006
# seed 2: gen_src_02 rows 47, 22, 95 (164); gen_src_04 78, 28, 78 (184).
#   gen_job_001.py (multi): out_001 <- src_03 JOIN src_04; out_002 <- src_03 JOIN
#                           src_01; out_003 <- src_03
#   gen_nb_002.ipynb: reads src_02 and src_04, uses both; writes 348 to out_004
#   gen_job_003.py: reads src_02 and src_01 (distractor); produces r001=164 to topic_01
#   gen_job_004.py: consumes r001=164; writes 164 to out_005
G = "gen_"
TINY = {
    1: {
        "values": {"gen_nb_002.ipynb": "INSERT INTO gen_out_004 VALUES (1, 220)",
                   "gen_job_003.py": "INSERT INTO gen_out_005 VALUES (1, 252)",
                   "gen_job_004.py": "INSERT INTO gen_out_006 VALUES (1, 252)"},
        "records": {"gen_job_003.py": ["r001=252", "r002=252"]},
        "edges": {
            ("src_04", "out_001", "job_001.py"), ("src_01", "out_002", "job_001.py"),
            ("src_03", "out_002", "job_001.py"), ("src_03", "out_003", "job_001.py"),
            ("src_04", "out_003", "job_001.py"), ("src_03", "out_004", "nb_002.ipynb"),
            ("src_04", "topic_01", "job_003.py"), ("src_02", "topic_01", "job_003.py"),
            ("src_04", "topic_02", "job_003.py"), ("src_02", "topic_02", "job_003.py"),
            ("src_04", "out_005", "job_003.py"), ("src_02", "out_005", "job_003.py"),
            ("topic_01", "out_006", "job_004.py"),
        },
        "runs": {("job_003.py", "job_004.py", "topic_01")},
        "provenance": {
            "out_001": {"src_04"}, "out_002": {"src_01", "src_03"},
            "out_003": {"src_03", "src_04"}, "out_004": {"src_03"},
            "out_005": {"src_02", "src_04"}, "out_006": {"src_02", "src_04", "topic_01"},
            "topic_01": {"src_02", "src_04"}, "topic_02": {"src_02", "src_04"},
        },
        "distractors": {"nb_002.ipynb": ["src_01"]},
    },
    2: {
        "values": {"gen_nb_002.ipynb": "INSERT INTO gen_out_004 VALUES (1, 348)",
                   "gen_job_004.py": "INSERT INTO gen_out_005 VALUES (1, 164)"},
        "records": {"gen_job_003.py": ["r001=164"]},
        "edges": {
            ("src_03", "out_001", "job_001.py"), ("src_04", "out_001", "job_001.py"),
            ("src_03", "out_002", "job_001.py"), ("src_01", "out_002", "job_001.py"),
            ("src_03", "out_003", "job_001.py"), ("src_02", "out_004", "nb_002.ipynb"),
            ("src_04", "out_004", "nb_002.ipynb"), ("src_02", "topic_01", "job_003.py"),
            ("topic_01", "out_005", "job_004.py"),
        },
        "runs": {("job_003.py", "job_004.py", "topic_01")},
        "provenance": {
            "out_001": {"src_03", "src_04"}, "out_002": {"src_01", "src_03"},
            "out_003": {"src_03"}, "out_004": {"src_02", "src_04"},
            "out_005": {"src_02", "topic_01"}, "topic_01": {"src_02"},
        },
        "distractors": {"job_003.py": ["src_01"]},
    },
}  # fmt: skip


@pytest.mark.parametrize("seed", sorted(TINY))
def test_tiny_seeded_workloads_match_the_hand_checked_truth(seed):
    expected = TINY[seed]
    key = generate.generate("tiny", seed, jobs=4)
    steps = {p["job"]: p["steps"] for p in key["processes"]}
    for job, sql in expected["values"].items():
        assert steps[job][-1] == {"sql": sql}
    for job, records in expected["records"].items():
        assert [s["record"] for s in steps[job] if "produce" in s] == records
    assert {(e["from"], e["to"], e["job"]) for e in key["dataset_edges"]} == {
        (G + a, G + b, G + j) for a, b, j in expected["edges"]
    }
    assert {(e["from_job"], e["to_job"], e["via"]) for e in key["run_edges"]} == {
        (G + a, G + b, G + v) for a, b, v in expected["runs"]
    }
    assert {p["dataset"]: set(p["upstream"]) for p in key["provenance"]} == {
        G + d: {G + u for u in ups} for d, ups in expected["provenance"].items()
    }
    assert key["generated"]["distractors"] == {
        G + j: [G + t for t in ts] for j, ts in expected["distractors"].items()
    }


@pytest.mark.parametrize("name", sorted(generate.KEYS))
def test_every_committed_key_regenerates_byte_for_byte(name):
    path = generate.path_for(name)
    assert path.read_bytes() == generate.committed()[name].encode("utf-8")


def test_exactly_the_configured_keys_are_committed():
    assert generate.generated_names() == sorted(generate.KEYS)
    assert generate.main(["--check"]) == 0


@pytest.mark.parametrize("name", sorted(generate.KEYS))
def test_a_committed_key_says_it_is_generated(name):
    key = generate.load_generated(name)
    seed, overrides = generate.KEYS[name]
    g = key["generated"]
    assert (g["generator"], g["version"], g["seed"]) == (
        generate.GENERATOR,
        generate.VERSION,
        seed,
    )
    assert g["parameters"] == generate.parameters(**overrides)
    assert g["hand_written"] is False
    assert key["description"].startswith("GENERATED, not hand-written")


def test_the_keys_have_the_sizes_the_task_asks_for():
    for name in generate.KEYS:
        jobs = len(generate.load_generated(name)["processes"])
        assert jobs == (100 if name == "scale_large" else 30), name


def test_generated_keys_stay_out_of_the_hand_written_set():
    """harness.workloads() (replay, live, score.py's pinned output) must not see them."""
    from harness import workloads

    assert not [w for w in workloads() if w.startswith("scale")]


@pytest.mark.parametrize("name", sorted(generate.KEYS))
def test_generated_programs_contain_no_dcp_code(name):
    key = generate.load_generated(name)
    for index, process in enumerate(key["processes"]):
        group = programs.group_id("run", name, index)
        if process["kind"] == "notebook":
            source = programs.notebook_source(programs.notebook(name, process, group))
        else:
            source = programs.script_source(name, process, group)
        assert programs.dcp_code_in(source) == [], process["job"]


def test_the_generator_imports_nothing_that_computes_lineage():
    tree = ast.parse(pathlib.Path(generate.__file__).read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in (
            node.names
            if isinstance(node, ast.Import)
            else [ast.alias(node.module or "")]
        )
    }
    assert imported <= {"argparse", "json", "pathlib", "random", "sys"}, imported
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import generate; "
        "generate.committed(); "
        "print(sorted(m for m in sys.modules if m.split('.')[0] in "
        "('dcp', 'app', 'dcp_openlineage', 'sqlglot', 'networkx', 'harness', 'score')))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code, str(GROUND_TRUTH)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "[]"


def test_the_committed_files_are_lf_and_end_with_one_newline():
    for name in generate.KEYS:
        data = generate.path_for(name).read_bytes()
        assert (
            b"\r" not in data and data.endswith(b"}\n") and not data.endswith(b"\n\n")
        )
        json.loads(data)


def test_a_different_seed_gives_a_different_workload():
    a = generate.generate("x", 1)
    b = generate.generate("x", 2)
    assert a["processes"] != b["processes"]
    assert generate.generate("x", 1) == a


def test_no_distractors_when_switched_off():
    key = generate.generate("x", 3, p_distractor=0.0)
    assert key["generated"]["distractors"] == {}
