"""run.py: which stages run, why the others are skipped, and the end-to-end flow."""

import json

import pytest
import run
from harness import workloads

ALL_OK = {"live": None, "openlineage": None, "uvicorn": None}
NO_SERVICES = {
    "live": "PostgreSQL is not reachable at localhost:5432",
    "openlineage": None,
    "uvicorn": None,
}


def statuses(planned):
    return {p["stage"]: (p["status"], p.get("reason")) for p in planned}


def test_everything_runs_when_everything_is_available():
    assert statuses(run.plan(None, ALL_OK)) == {s: ("run", None) for s in run.STAGES}


def test_live_stages_are_skipped_with_the_reason():
    planned = statuses(run.plan(None, NO_SERVICES))
    reason = NO_SERVICES["live"]
    assert planned == {
        "replay": ("run", None),
        "live": ("skipped", reason),
        "adversarial": ("skipped", reason),
        "scale": ("run", None),  # its replay half needs nothing; live is skipped inside
        "overhead": ("skipped", reason),
        "cpu": ("run", None),
    }


def test_each_stage_names_its_own_missing_library():
    probes = dict(ALL_OK, openlineage="missing openlineage", uvicorn="missing uvicorn")
    planned = statuses(run.plan(None, probes))
    assert planned["live"] == ("run", None)
    assert planned["adversarial"] == ("skipped", "missing openlineage")
    assert planned["overhead"] == ("skipped", "missing uvicorn")


def test_only_selects_stages():
    planned = statuses(run.plan(["cpu", "replay"], NO_SERVICES))
    assert planned["cpu"] == ("run", None) and planned["replay"] == ("run", None)
    assert {planned[s][0] for s in ("live", "adversarial", "overhead")} == {
        "not requested"
    }


def test_parse_only():
    assert run.parse_only(None) is None
    assert run.parse_only("replay, cpu") == ["replay", "cpu"]
    with pytest.raises(ValueError, match="unknown stage"):
        run.parse_only("replay,warp")


def score_rows(*rows):
    return [{"label": label, "hits": h, "found": f, "expected": e, "notes": []}
            for label, h, f, e in rows]  # fmt: skip


def live_workload(name, dcp_rows, exit_code=0):
    return {
        "workload": name,
        "processes": [{"program": f"{name}.py", "exit_code": exit_code}],
        "score": {"dcp": dcp_rows, "openlineage": []},
    }


GOOD = score_rows(("nodes", 3, 3, 3), ("run edges", 0, 0, 0))
FAN_IN = score_rows(
    ("nodes", 4, 4, 4),
    ("upstream(daily_revenue) run-level", 2, 2, 2),
    ("upstream(daily_revenue) dataset-level baseline", 2, 3, 2),
)


def test_cases_are_demonstrated_from_live_results():
    live = {"workloads": [live_workload("dark_zone", GOOD), live_workload("notebook", GOOD),
                          live_workload("topic_fan_in", FAN_IN)]}  # fmt: skip
    cases = run.evaluate_cases(live, {"events_received_uninstrumented": 0})
    assert [c["status"] for c in cases] == ["demonstrated live"] * 3
    assert cases[0]["openlineage_events_without_dcp"] == 0
    assert cases[2]["dataset_level_over_approximates"] is True


def test_a_wrong_graph_is_not_demonstrated():
    bad = score_rows(("nodes", 2, 3, 3))
    live = {"workloads": [live_workload("dark_zone", bad)]}
    cases = run.evaluate_cases(live, None)
    assert cases[0]["status"] == "NOT demonstrated"
    assert [c["status"] for c in cases[1:]] == ["not run", "not run"]


def test_baseline_rows_are_not_part_of_dcps_graph():
    rows = score_rows(
        ("nodes", 1, 1, 1), ("upstream(x) dataset-level baseline", 1, 2, 1)
    )
    assert run.perfect(rows)
    assert not run.perfect(rows + score_rows(("upstream(x) run-level", 1, 2, 1)))


def test_case_3_needs_the_baseline_to_over_approximate():
    flat = score_rows(("upstream(daily_revenue) dataset-level baseline", 2, 2, 2))
    live = {"workloads": [live_workload("topic_fan_in", flat)]}
    (case,) = [c for c in run.evaluate_cases(live, None) if c["case"] == 3]
    assert case["status"] == "NOT demonstrated"


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(run, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(run, "DOCS_DIR", tmp_path)
    monkeypatch.setattr(run, "probe", lambda: dict(NO_SERVICES))
    monkeypatch.setattr(run, "postgres_version", lambda: None)
    return tmp_path


def test_replay_only_end_to_end(isolated):
    assert run.main(["--label", "unit", "--only", "replay"]) == 0
    results = json.loads((isolated / "results" / "unit" / "results.json").read_text())
    assert [w["workload"] for w in results["replay"]["workloads"]] == workloads()
    assert statuses(results["stages"])["replay"][0] == "ran"
    md = (isolated / "P5-unit.md").read_text(encoding="utf-8")
    assert md.startswith("# P5 results: `unit`")
    assert "## Ground truth: replay" in md
    assert results["environment"]["git_commit"]


def test_skipped_stages_are_rendered_with_their_reason(isolated):
    assert run.main(["--label", "unit", "--only", "replay,live"]) == 0
    md = (isolated / "P5-unit.md").read_text(encoding="utf-8")
    assert "| live | skipped |" in md and NO_SERVICES["live"] in md


def test_a_failed_stage_is_rendered_and_fails_the_run(isolated, monkeypatch):
    def boom(_events_for):
        raise RuntimeError("scoring exploded")

    monkeypatch.setattr(run, "score_all", boom)
    assert run.main(["--label", "unit", "--only", "replay"]) == 1
    md = (isolated / "P5-unit.md").read_text(encoding="utf-8")
    assert "| replay | failed |" in md and "scoring exploded" in md


def test_a_python_that_cannot_run_the_cpu_stage_is_recorded(tmp_path):
    result = run.run_cpu(["dcp-no-such-python"], tmp_path, log=lambda _: None)
    (entry,) = result["pythons"]
    assert entry["executable"] == "dcp-no-such-python" and "error" in entry


def test_labels_are_slugs(isolated):
    with pytest.raises(SystemExit):
        run.main(["--label", "../escape"])


# A1: the pinned benchmark environment


def test_marker_applies():
    assert run.marker_applies(None, (3, 10, 4))
    assert run.marker_applies('python_version < "3.11"', (3, 10, 4))
    assert not run.marker_applies('python_version < "3.11"', (3, 11, 0))
    assert run.marker_applies("python_version >= '3.11'", (3, 14, 8))
    with pytest.raises(ValueError, match="unsupported environment marker"):
        run.marker_applies('sys_platform == "win32"', (3, 12, 0))


def test_read_pins_applies_markers_and_normalises_names(tmp_path):
    req = tmp_path / "requirements.txt"
    req.write_text(
        '# comment\npsycopg[binary]==3.3.6\nipykernel==7.4.0; python_version >= "3.11"\n'
        'ipykernel==7.3.0; python_version < "3.11"\nnot-pinned>=1\n',
        encoding="utf-8",
    )
    con = tmp_path / "constraints.txt"
    con.write_text(
        "Jupyter_Client==8.10.0  # trailing comment\npsycopg==3.3.6\n", encoding="utf-8"
    )
    pins = run.read_pins([req, con], python=(3, 10, 20))
    assert pins == {
        "psycopg": "3.3.6",
        "ipykernel": "7.3.0",
        "jupyter-client": "8.10.0",
    }
    assert run.read_pins([req], python=(3, 12, 3))["ipykernel"] == "7.4.0"


def test_read_pins_refuses_a_contradiction(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_text("sqlglot==1.0\n", encoding="utf-8")
    b.write_text("sqlglot==2.0\n", encoding="utf-8")
    with pytest.raises(ValueError, match="two versions"):
        run.read_pins([a, b])


def test_pin_check_records_mismatches_without_failing():
    installed = {"sqlglot": "30.21.0", "uvicorn": "0.53.0"}.get
    result = run.pin_check(
        {"sqlglot": "30.21.0", "uvicorn": "0.54.0", "nbclient": "0.11.0"}, installed
    )
    assert result["checked"] == 3
    assert result["mismatches"] == [
        {"package": "nbclient", "pinned": "0.11.0", "installed": None},
        {"package": "uvicorn", "pinned": "0.54.0", "installed": "0.53.0"},
    ]


def test_the_committed_pin_files_parse_for_every_supported_python():
    for python in ((3, 10, 0), (3, 12, 0), (3, 14, 0)):
        pins = run.read_pins(python=python)
        for name in ("sqlglot", "psycopg", "psycopg-binary", "confluent-kafka", "fastapi",
                     "uvicorn", "networkx", "jsonschema", "nbclient", "ipykernel"):  # fmt: skip
            assert name in pins, (python, name)


def test_the_environment_table_shows_the_pin_check():
    import render

    env = {
        "pins": {
            "files": ["benchmarks/requirements.txt"],
            "checked": 2,
            "mismatches": [],
        }
    }
    assert (
        render._pins(env["pins"]) == "all 2 pins match (`benchmarks/requirements.txt`)"
    )
    env["pins"]["mismatches"] = [
        {"package": "uvicorn", "pinned": "0.54.0", "installed": None}
    ]
    assert "1 of 2 differ" in render._pins(env["pins"])
    assert "uvicorn not installed (pinned 0.54.0)" in render._pins(env["pins"])


# P5.1 (B3, B4): the scale stage. Unit CI replays every generated key here.


def test_scale_replays_every_generated_key_and_skips_live_with_the_reason(isolated):
    import generate

    assert run.main(["--label", "unit", "--only", "scale"]) == 0
    results = json.loads((isolated / "results" / "unit" / "results.json").read_text())
    scale_results = results["scale"]
    assert sorted(scale_results["replay"]["scores"]) == sorted(generate.KEYS)
    assert scale_results["live"] == {"skipped": NO_SERVICES["live"]}
    summary = scale_results["replay"]["summary"]
    # Every recall loss is OpenLineage core losing an edge to a split run;
    # DCP, the baseline and the facet reading miss nothing.
    assert all(not m["unexplained"] for m in summary["misses"].values())
    for name, scored in scale_results["replay"]["scores"].items():
        for row in scored["dcp"] + scored["openlineage"]:
            if not row["label"].startswith("openlineage provenance(") and (
                row["label"] != "openlineage dataset edges"
            ):
                assert row["hits"] == row["expected"], (name, row["label"])
    # Everything DCP finds beyond the truth is a distractor read, and there is some.
    assert all(not e["unexplained"] for e in summary["extras"].values())
    assert sum(e["extras"] for e in summary["extras"].values()) > 0
    md = (isolated / "P5-unit.md").read_text(encoding="utf-8")
    assert "## Ground truth at scale: generated keys (added in P5.1)" in md
    assert "#### scale_s01 … scale_s10 (10 keys), micro-averaged" in md
    assert "#### scale_large, on its own" in md
    assert (
        "## Ground truth: replay" not in md
    )  # never pooled with the hand-written keys


def test_quick_mode_runs_one_small_seed_live():
    assert run.QUICK_SCALE_LIVE == ("scale_s01",)
