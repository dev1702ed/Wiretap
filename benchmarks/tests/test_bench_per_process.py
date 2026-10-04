"""Scoring the per-process OpenLineage mapping (P5.2, A3): new rows and a new
method, appended; every existing row unchanged."""

import json

import pytest
import render
import scale
from generate import generated_names, load_generated
from harness import load, replay, workloads
from run import _rows_agree
from score import format_table, report_lines, score_all, score_workload

pytest.importorskip("app.graph")


def row(label, hits, found, expected, notes=()):
    return {"label": label, "hits": hits, "found": found, "expected": expected,
            "notes": list(notes)}  # fmt: skip


@pytest.mark.parametrize(
    ("label", "level"),
    [
        ("openlineage (per process) dataset edges", "dataset edges"),
        ("openlineage (per process) provenance(gen_out_001)", "provenance"),
    ],
)
def test_per_process_rows_have_their_own_method(label, level):
    assert scale.method_level(label) == ("OpenLineage core (per process)", level)


def test_the_per_process_method_comes_after_every_existing_method():
    assert scale.METHODS[-1] == "OpenLineage core (per process)"
    assert scale.METHODS[:4] == (
        "DCP run-level",
        "dataset-level baseline",
        "OpenLineage core",
        "OpenLineage + dcp facet",
    )


def test_every_workload_gets_per_process_rows_for_every_level():
    for name in workloads():
        key = load(name)
        scored = score_workload(key, replay(key))
        labels = [r["label"] for r in scored["openlineage_per_process"]]
        assert labels == ["openlineage (per process) dataset edges"] + [
            f"openlineage (per process) provenance({p['dataset']})"
            for p in key["provenance"]
        ]


def test_hand_written_keys_score_the_same_in_both_mappings():
    """None of the hand-written keys has a process that joins two traces (§3)."""
    for name in workloads():
        key = load(name)
        scored = score_workload(key, replay(key))
        default = [r for r in scored["openlineage"] if "dcp facet" not in r["label"]]
        per_process = scored["openlineage_per_process"]
        assert [
            (r["hits"], r["found"], r["expected"], r["notes"]) for r in default
        ] == [(r["hits"], r["found"], r["expected"], r["notes"]) for r in per_process]


def test_the_per_process_section_is_printed_after_the_existing_ones():
    lines = report_lines(score_all(replay))
    for name in workloads():
        old = lines.index(
            f"-- {name}: OpenLineage translation (core run model, then with the dcp facet)"
        )
        new = lines.index(
            f"-- {name}: OpenLineage translation, one run per process "
            "(core run model; added in P5.2)"
        )
        assert new > old
        assert lines[new - 1] == ""


def test_a_long_label_widens_only_its_own_table():
    long_label = "openlineage (per process) provenance(refund_summary)"  # 52 characters
    from score import fitted_table

    (header, line) = fitted_table([row(long_label, 1, 1, 1)])
    assert line.startswith(long_label + " 1/1 = 1.000")
    assert header.startswith("level" + " " * 48 + "precision")
    assert format_table([row("nodes", 1, 1, 1)])[1].startswith(
        "nodes" + " " * 47 + "1/1"
    )


def test_scale_keys_lose_no_item_per_process():
    """§3: recall 1.0 at every level on the existing scale keys, and every
    per-process miss would be unexplained (none can be a split run)."""
    for name in [n for n in generated_names() if n.startswith("scale_")]:
        key = load_generated(name)
        scored = score_workload(key, replay(key))
        assert scale.per_process_misses(scored) == []
        cells = scale.totals(scored)
        for level in ("dataset edges", "provenance"):
            cell = cells[("OpenLineage core (per process)", level)]
            assert cell["hits"] == cell["expected"], (name, level)


def test_a_per_process_miss_is_never_explained_by_a_split_run():
    key = {"dataset_edges": [{"from": "t", "to": "out", "job": "c.py"}]}
    scored = {
        "dcp": [],
        "openlineage": [row("openlineage dataset edges", 0, 0, 1, ["-t->out (c.py)"])],
        "openlineage_per_process": [
            row("openlineage (per process) dataset edges", 0, 0, 1, ["-t->out (c.py)"]),
            row("openlineage (per process) provenance(out)", 0, 0, 1, ["-t"]),
        ],
    }
    m = scale.explain_misses(key, scored, ["c.py"])
    assert (m["misses"], m["explained_by_split_runs"]) == (3, 1)
    assert m["unexplained"] == [
        "openlineage (per process) dataset edges: -t->out (c.py)",
        "openlineage (per process) provenance(out): -t",
    ]
    assert scale.per_process_misses(scored) == m["unexplained"]


def test_aggregate_has_the_per_process_method_last():
    scored = {
        "dcp": [row("nodes", 1, 1, 1)],
        "openlineage": [row("openlineage dataset edges", 1, 2, 1)],
        "openlineage_per_process": [
            row("openlineage (per process) dataset edges", 1, 3, 1)
        ],
    }
    rows = scale.aggregate([scored])
    assert [(r["method"], r["level"]) for r in rows] == [
        ("DCP run-level", "nodes"),
        ("OpenLineage core", "dataset edges"),
        ("OpenLineage core (per process)", "dataset edges"),
    ]
    assert rows[-1]["found"] == 3


def test_live_and_replay_agreement_covers_the_per_process_rows():
    a = {"dcp": [], "openlineage": [], "openlineage_per_process": [row("x", 1, 1, 1)]}
    b = json.loads(json.dumps(a))
    assert _rows_agree(a, b)
    b["openlineage_per_process"][0]["found"] = 2
    assert not _rows_agree(a, b)


def test_render_shows_the_per_process_table_only_when_scored():
    key = load("topic_fan_in")
    scored = score_workload(key, replay(key))
    shown = render._scores([scored])
    assert any("one run per process" in line for line in shown)
    assert any(
        line.startswith("openlineage (per process) provenance(") for line in shown
    )
    older = {k: v for k, v in scored.items() if k != "openlineage_per_process"}
    assert not any("one run per process" in line for line in render._scores([older]))
    assert shown[: len(render._scores([older]))] == render._scores([older])
