"""Scoring at scale (P5.1, B3): grouping rows by method and level, micro-averaging."""

import pytest
import scale
from live import seed


def row(label, hits, found, expected, notes=()):
    return {
        "label": label,
        "hits": hits,
        "found": found,
        "expected": expected,
        "notes": list(notes),
    }


@pytest.mark.parametrize(
    ("label", "method", "level"),
    [
        ("nodes", "DCP run-level", "nodes"),
        ("dataset edges", "DCP run-level", "dataset edges"),
        ("run edges", "DCP run-level", "run edges"),
        ("upstream(gen_out_001) run-level", "DCP run-level", "provenance"),
        (
            "upstream(gen_out_001) dataset-level baseline",
            "dataset-level baseline",
            "provenance",
        ),
        ("openlineage dataset edges", "OpenLineage core", "dataset edges"),
        ("openlineage provenance(gen_out_001)", "OpenLineage core", "provenance"),
        (
            "openlineage + dcp facet provenance(gen_out_001)",
            "OpenLineage + dcp facet",
            "provenance",
        ),
    ],
)
def test_every_score_row_has_one_method_and_level(label, method, level):
    assert scale.method_level(label) == (method, level)


def test_an_unknown_row_is_refused():
    with pytest.raises(ValueError, match="unknown score row"):
        scale.method_level("vibes")


def scored(*dcp, ol=()):
    return {"dcp": list(dcp), "openlineage": list(ol)}


def test_micro_average_sums_before_dividing():
    a = scored(
        row("upstream(x) run-level", 1, 1, 1), row("upstream(y) run-level", 1, 3, 1)
    )
    b = scored(row("upstream(z) run-level", 4, 4, 4))
    (prov,) = [r for r in scale.aggregate([a, b]) if r["level"] == "provenance"]
    assert (prov["hits"], prov["found"], prov["expected"]) == (6, 8, 6)
    assert prov["precision"] == pytest.approx(6 / 8)  # not the mean of 0.5 and 1.0
    assert prov["recall"] == 1.0
    assert prov["per_key_precision"] == {"min": 0.5, "median": 0.75, "max": 1.0}
    assert prov["keys"] == 2


def test_a_level_with_nothing_found_has_no_precision():
    (runs,) = scale.aggregate([scored(row("run edges", 0, 0, 0))])
    assert runs["precision"] is None and runs["recall"] is None
    assert runs["per_key_precision"] is None


def test_extras_are_checked_against_the_distractor_reads():
    key = {"generated": {"distractors": {"gen_job_002.py": ["gen_src_09"]}}}
    s = scored(
        row("dataset edges", 2, 3, 2, ["+gen_src_09->gen_out_001 (gen_job_002.py)"]),
        row("upstream(gen_out_001) run-level", 1, 2, 1, ["+gen_src_09"]),
        row("upstream(gen_out_002) run-level", 1, 2, 1, ["+gen_src_01"]),
        row("upstream(gen_out_001) dataset-level baseline", 1, 4, 1, ["+gen_src_07"]),
    )
    e = scale.explain_extras(key, s)
    assert (e["extras"], e["explained_by_distractors"]) == (3, 2)
    assert e["unexplained"] == ["upstream(gen_out_002) run-level: +gen_src_01"]


def test_a_job_on_two_traces_is_split():
    def ev(job, trace):
        return {"job": {"name": job}, "trace_id": trace}

    events = [ev("a.py", "t1"), ev("c.py", "t1"), ev("c.py", "t2"), ev("b.py", "t2")]
    assert scale.split_jobs(events) == ["c.py"]


def test_only_openlineage_core_misses_on_a_split_job_are_explained():
    key = {"dataset_edges": [{"from": "t", "to": "out", "job": "c.py"}]}
    s = scored(
        row("nodes", 1, 1, 2, ["-gen_src_09"]),
        ol=[
            row(
                "openlineage dataset edges", 0, 0, 1, ["-t->out (c.py)", "-s->x (d.py)"]
            ),
            row("openlineage provenance(out)", 0, 0, 1, ["-t"]),
            row("openlineage + dcp facet provenance(out)", 0, 0, 1, ["-t"]),
        ],
    )
    m = scale.explain_misses(key, s, ["c.py"])
    assert (m["misses"], m["explained_by_split_runs"]) == (5, 2)
    assert m["unexplained"] == [
        "nodes: -gen_src_09",
        "openlineage dataset edges: -s->x (d.py)",
        "openlineage + dcp facet provenance(out): -t",
    ]


def test_misses_list_every_recall_loss():
    s = scored(
        row("nodes", 1, 1, 2, ["-gen_src_01"]),
        ol=[row("openlineage dataset edges", 1, 1, 1)],
    )
    assert scale.misses(s) == ["nodes: -gen_src_01"]


def test_seeds_and_scale_large_are_kept_apart():
    key = {
        "workload": "k",
        "processes": [],
        "datasets": {},
        "provenance": [],
        "dataset_edges": [],
    }
    s = scored(row("nodes", 1, 1, 1))
    summary = scale.summarize(
        {
            "scale_s01": dict(key, workload="scale_s01"),
            "scale_large": dict(key, workload="scale_large"),
        },
        {"scale_s01": s, "scale_large": s},
        {"scale_s01": [], "scale_large": []},
    )
    assert summary["seeds"]["names"] == ["scale_s01"]
    assert list(summary["others"]) == ["scale_large"]


def test_a_generated_key_seeds_its_own_tables():
    key = {
        "tables": {
            "gen_out_001": {"columns": "id int, v int", "rows": []},
            "gen_src_01": {"columns": "id int, v int", "rows": [[1, 5], [2, 7]]},
        },
        "topics": ["gen_topic_01"],
    }
    assert seed.key_seed_sql(key) == [
        "DROP TABLE IF EXISTS gen_out_001, gen_src_01",
        "CREATE TABLE gen_out_001 (id int, v int)",
        "CREATE TABLE gen_src_01 (id int, v int)",
        "INSERT INTO gen_src_01 VALUES (1, 5), (2, 7)",
    ]
