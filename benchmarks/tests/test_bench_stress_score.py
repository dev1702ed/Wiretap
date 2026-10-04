"""Scoring the stress set (P5.2, B4): its own group, every miss explained by a
named cause, and the per-cause table.

The causes are checked on tiny hand-made plans whose losses were worked out
by hand (below), then on every committed stress key.
"""

import json
import pathlib

import generate
import pytest
import render
import run
import scale
from harness import replay
from score import score_workload

pytest.importorskip("app.graph")

S1, S2, S3, S4 = "gen_src_01", "gen_src_02", "gen_src_03", "gen_src_04"
T1 = "gen_topic_01"
O1, O2, O3, O4 = (f"gen_out_00{i}" for i in range(1, 5))
MULTI = "multi-record consumer: earlier record's parent dropped (job-level keeps the latest read per dataset)"
STORE = "store-mediated: Postgres read carries no parents"

# p1 uses S1, p2 uses S2, p3 uses S3 (and reads S4 as a distractor), all to T1.
# c.py consumes r001 (p1), r003 (p3), r002 (p2): truth {T1, S1, S2, S3}; DCP keeps
# the last read of T1 (r002, p2), so it is predicted to lose S1 and S3.
# m.py writes O1 from S1 JOIN S2; a.py reads O1, writes O2 (chain 1); b.py reads
# O2, writes O3 (chain 2). DCP stops at the table read: it loses upstream(O1) =
# {S1, S2} on O2, and upstream(O2) = {O1, S1, S2} on O3.
PLAN = {
    "rows": {S1: [[1, 10]], S2: [[1, 5]], S3: [[1, 1]], S4: [[1, 9]]},
    "jobs": [
        {"kind": "script", "job": "p1.py", "reads": [S1], "used": [S1],
         "outputs": [["produce", T1, "r001"]]},
        {"kind": "script", "job": "p2.py", "reads": [S2], "used": [S2],
         "outputs": [["produce", T1, "r002"]]},
        {"kind": "script", "job": "p3.py", "reads": [S3, S4], "used": [S3],
         "outputs": [["produce", T1, "r003"]]},
        {"kind": "consumer", "job": "c.py", "out": O4,
         "steps": [["consume", T1, "r001"], ["consume", T1, "r003"], ["consume", T1, "r002"]]},
        {"kind": "multi", "job": "m.py", "steps": [["insert_select", O1, [S1, S2]]]},
        {"kind": "store", "job": "a.py", "reads": [O1], "used": [O1], "out": O2},
        {"kind": "store", "job": "b.py", "reads": [O2], "used": [O2], "out": O3},
    ],
}  # fmt: skip


@pytest.fixture(scope="module")
def key():
    return generate.derive("hand", PLAN, {"seed": None})


@pytest.fixture(scope="module")
def scored(key):
    events = replay(key)
    return score_workload(key, events), scale.split_jobs(events)


def test_predicted_losses_match_the_hand_analysis(key):
    losses = scale.predicted_losses(key)
    assert losses[O4] == {MULTI: {S1, S3}}
    assert losses[O2] == {STORE: {S1, S2}}
    assert losses[O3] == {STORE: {O1, S1, S2}}
    assert O1 not in losses and T1 not in losses


def test_every_dcp_miss_carries_its_named_cause(key, scored):
    s, split = scored
    m = scale.explain_stress_misses(key, s, split)
    assert m["unexplained"] == []
    # DCP and the facet reader each miss S1, S3 (multi-record) and S1, S2, O1, S1, S2 (store)
    assert m["by_method"]["DCP run-level"] == {MULTI: 2, STORE: 5, "split run": 0}
    assert m["by_method"]["OpenLineage + dcp facet"] == m["by_method"]["DCP run-level"]
    assert "OpenLineage core (per process)" not in m["by_method"]
    assert m["misses"] == 14  # 7 + 7: nothing else lost anything


def test_dcp_loses_exactly_the_predicted_items(key, scored):
    s, _ = scored
    rows = {r["label"]: r for r in s["dcp"]}
    assert rows[f"upstream({O4}) run-level"]["notes"] == [f"-{S1}", f"-{S3}"]
    assert rows[f"upstream({O2}) run-level"]["notes"] == [f"-{S1}", f"-{S2}"]
    assert rows[f"upstream({O3}) run-level"]["notes"] == [f"-{O1}", f"-{S1}", f"-{S2}"]
    baseline = rows[f"upstream({O3}) dataset-level baseline"]
    assert baseline["hits"] == baseline["expected"]  # reachability crosses the tables


def test_a_miss_without_a_predicted_cause_is_unexplained(key, scored):
    _, split = scored
    fake = {
        "dcp": [
            {
                "label": f"upstream({O4}) run-level",
                "notes": [f"-{S2}"],
            },  # p2 is last: kept
            {"label": "run edges", "notes": ["-p1.py->c.py via gen_topic_01"]},
            {"label": f"upstream({O2}) dataset-level baseline", "notes": [f"-{S1}"]},
        ],
        "openlineage": [],
        "openlineage_per_process": [
            {
                "label": f"openlineage (per process) provenance({O2})",
                "notes": [f"-{S1}"],
            }
        ],
    }
    m = scale.explain_stress_misses(key, fake, split)
    assert m["misses"] == 4
    assert len(m["unexplained"]) == 4


def test_split_losses_follow_the_truth_through_a_store_read():
    key = {
        "provenance": [
            {"dataset": "t", "upstream": ["s1", "s2"]},
            {"dataset": "o", "upstream": ["t", "s1", "s2"]},
            {"dataset": "o2", "upstream": ["o", "t", "s1", "s2"]},
        ],
        "dataset_edges": [
            {"from": "s1", "to": "t", "job": "p1"},
            {"from": "s2", "to": "t", "job": "p2"},
            {"from": "t", "to": "o", "job": "c"},
            {"from": "o", "to": "o2", "job": "store"},
        ],
    }
    losses = scale.split_losses(key, ["c"])
    assert losses["o"] == {"t", "s1", "s2"}
    assert losses["o2"] == {"t", "s1", "s2"}  # upstream of o, whose writer split
    assert losses["t"] == set()
    assert scale.split_losses(key, []) == {"t": set(), "o": set(), "o2": set()}


def test_every_committed_stress_key_is_fully_explained():
    """Rule 4, on the committed stress set in replay: every extra a distractor
    read, every miss a named cause."""
    for name in generate.stress_names():
        key = generate.load_generated(name)
        events = replay(key)
        s = score_workload(key, events)
        extras = scale.explain_extras(key, s)
        assert extras["unexplained"] == [], name
        misses = scale.explain_stress_misses(key, s, scale.split_jobs(events))
        assert misses["unexplained"] == [], name
        dcp = misses["by_method"].get("DCP run-level", {})
        assert sum(dcp.values()) == sum(
            n for r in s["dcp"] for n in [sum(x.startswith("-") for x in r["notes"])]
        )


def test_the_stress_summary_keeps_seeds_and_the_large_key_apart(key, scored):
    s, split = scored
    keys = {"stress_s01": key, "stress_large": key}
    summary = scale.summarize_stress(
        keys, {n: s for n in keys}, {n: split for n in keys}
    )
    assert summary["seeds"]["names"] == ["stress_s01"]
    assert list(summary["others"]) == ["stress_large"]
    (described,) = [k for k in summary["keys"] if k["workload"] == "hand"][:1]
    assert described["store_read_jobs"] == 2
    assert described["store_chains_of_two"] == 1
    assert described["multi_record_consumers"] == 1
    assert described["records_consumed_by_them"] == 3
    assert described["kinds"]["store-read"] == 2


def test_the_scale_stage_scores_the_stress_set_apart(tmp_path):
    out = run.run_scale(
        tmp_path, quick=True, probes={"live": "no services"}, log=lambda m: None
    )
    assert sorted(out["replay"]["scores"]) == generate.generated_names()
    assert sorted(out["stress"]["replay"]["scores"]) == generate.stress_names()
    assert not [
        k
        for k in out["replay"]["summary"]["keys"]
        if k["workload"].startswith("stress")
    ]
    assert out["generator_version"] == "1.0"
    assert out["stress"]["generator_version"] == "1.1"
    assert out["stress"]["live"] == {"skipped": "no services"}
    assert run.QUICK_STRESS_LIVE == ("stress_s01",)


def test_the_stress_section_renders_on_its_own(tmp_path):
    out = run.run_scale(
        tmp_path, quick=True, probes={"live": "no services"}, log=lambda m: None
    )
    results = {"scale": out}
    lines = render._stress(results)
    assert (
        lines[0]
        == "## Ground truth: the stress set, DCP's known failure modes (added in P5.2)"
    )
    text = "\n".join(lines)
    assert "#### stress_s01 … stress_s05 (5 keys), micro-averaged" in text
    assert "#### stress_large, on its own" in text
    assert f"DCP: {MULTI}" in text and f"DCP: {STORE}" in text
    assert "**stress_s01 … stress_s05, total**" in text
    assert "Skipped: no services" in text
    assert (
        render._stress({"scale": {k: v for k, v in out.items() if k != "stress"}}) == []
    )
    assert "stress" not in "\n".join(render._scale(results))

    # A P5.1 results file (no stress group) renders without the section.
    fixture = pathlib.Path(__file__).parent / "data" / "render_p51_fixture.json"
    rendered = render.render(json.loads(fixture.read_text(encoding="utf-8")))
    assert "stress set" not in rendered
