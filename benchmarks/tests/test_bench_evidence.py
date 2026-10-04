"""The paper evidence pack (P5.2, C4): extraction from fixture records, the
newest-record rule, the owner's machine, the README block, determinism."""

import pathlib

import evidence
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def env(
    started,
    commit="abc123",
    os_name="Synthetic-OS",
    cpu="Synthetic CPU, 4 logical cores",
):
    return [
        "## Environment",
        "",
        "|  |  |",
        "|---|---|",
        f"| Started (UTC) | {started} |",
        f"| Git commit | `{commit}` |",
        "| Working tree dirty | False |",
        f"| OS | {os_name} |",
        f"| CPU | {cpu} |",
        "",
    ]


ADVERSARIAL = [
    "## Adversarial",
    "",
    "| Case | Movement | Workload | Status | Evidence |",
    "|---|---|---|---|---|",
    "| 1 | Ad-hoc script | `dark_zone` | demonstrated live | DCP graph matches the key |",
    "",
    "### OpenLineage baseline, measured",
    "",
    "| Measurement | Value |",
    "|---|---|",
    "| Events received from the uninstrumented programs | 0 |",
    "",
]
LIVE = ["## Ground truth: live", "", "Real PostgreSQL.", ""]
for _w in ("dark_zone", "job_granularity", "notebook", "topic_fan_in"):
    LIVE += [f"### {_w}", "", "```", f"level  {_w}", "```", ""]


def method_table(per_key, dcp="1/1 = 1.000", tag=""):
    header = "| Method | Level | Precision | Recall |" + (" Keys |" if per_key else "")
    sep = "|---|---|---|---|" + ("---|" if per_key else "")
    extra = " 2 |" if per_key else ""
    return [
        header,
        sep,
        f"| DCP run-level | nodes | {dcp} | {dcp} |{extra}",
        f"| DCP run-level | provenance | {dcp}{tag} | {dcp} |{extra}",
        f"| dataset-level baseline | provenance | 1/2 = 0.500 | 1/1 = 1.000 |{extra}",
        f"| OpenLineage core | provenance | 1/3 = 0.333 | 1/1 = 1.000 |{extra}",
        f"| OpenLineage core (per process) | provenance | 1/4 = 0.250 | 1/1 = 1.000 |{extra}",
    ]


SCALE = [
    "## Ground truth at scale: generated keys (added in P5.1)",
    "",
    "| Key | Seed |",
    "|---|---|",
    "| scale_s01 | 1 |",
    "",
    "### Replay",
    "",
    "#### scale_s01 … scale_s02 (2 keys), micro-averaged",
    "",
    *method_table(True, tag=" replay"),
    "",
    "### Live",
    "",
    "#### scale_s01 … scale_s02 (2 keys), micro-averaged",
    "",
    *method_table(True),
    "",
]
STRESS = [
    "## Ground truth: the stress set, DCP's known failure modes (added in P5.2)",
    "",
    "| Key | Seed |",
    "|---|---|",
    "| stress_s01 | 201 |",
    "",
    "### Stress set: replay",
    "",
    "#### stress_s01 … stress_s02 (2 keys), micro-averaged",
    "",
    *method_table(True),
    "",
    "### Stress set: live",
    "",
    "Skipped: no services",
    "",
]


def overhead(p99_verdict):
    return [
        "## Overhead: live (4b)",
        "",
        "### T1 point read",
        "",
        "| Config | p50 |",
        "|---|---|",
        "| base | 100.0 |",
        "",
        "| Config | Added p99 µs [95% CI] | < 1 ms p99 added | < 2% throughput loss |",
        "|---|---|---|---|",
        f"| file | +1.0 [+0.5, +1.5] | {p99_verdict} | not met |",
        "",
        "### Process start-up (excluded from per-call timing)",
        "",
        "| Command | p50 |",
        "|---|---|",
        "| python | 14.0 |",
        "",
    ]


FIXED = [
    "### The fixed cost per call and the < 2% throughput target",
    "",
    "| Tier | Config | Implied µs/call [95% CI] | Loss < 2% for queries slower than (µs) |",
    "|---|---|---|---|",
    "| T1 point read | file | +50.0 [+40.0, +60.0] | 2450.0 |",
    "",
]


@pytest.fixture
def repo(tmp_path):
    results = tmp_path / "results"
    results.mkdir()

    def write(name, lines):
        (results / name).write_text(
            "\n".join([f"# {name}", "", *lines]) + "\n", encoding="utf-8"
        )

    write(
        "P5-sandbox-a.md",
        env("2026-01-01T00:00:00+00:00", "sandboxcommit")
        + ADVERSARIAL
        + LIVE
        + SCALE
        + STRESS
        + overhead("met")
        + FIXED,
    )
    write("P5-local-old.md", env("2025-12-01T00:00:00+00:00", "oldowner") + ADVERSARIAL)
    write(
        "P5-local-new.md",
        env("2026-02-01T00:00:00+00:00", "ownercommit", "Windows-11", "Owner CPU")
        + overhead("inconclusive"),
    )
    readme = tmp_path / "README.md"
    readme.write_text(
        f"# Title\n\nBefore.\n\n{evidence.START}\nold\n{evidence.END}\n\nAfter.\n",
        encoding="utf-8",
    )
    return tmp_path, results, readme


def run(repo, *extra):
    tmp, results, readme = repo
    out = tmp / "paper" / "evidence.md"
    args = [
        "--results",
        str(results),
        "--out",
        str(out),
        "--readme",
        str(readme),
        *extra,
    ]
    return evidence.main(args), out


def test_every_claim_takes_the_newest_record_that_has_it(repo):
    records = evidence.load(repo[1])
    by_key = {c.key: c for c in evidence.claims(records)}
    assert {b.record.name for b in by_key["C1"].blocks} == {"P5-sandbox-a.md"}
    assert {b.record.name for b in by_key["C6"].blocks} == {
        "P5-local-new.md"
    }  # the owner's
    assert by_key["C6"].blocks[0].record.owner
    assert "the owner's machine: Windows-11; Owner CPU" in evidence._source_line(
        by_key["C6"].blocks[0]
    )
    assert [b.record.name for b in by_key["C7"].blocks] == ["P5-local-new.md"]
    assert [b.record.name for b in by_key["C8"].blocks] == ["P5-sandbox-a.md"]
    assert not any(c.missing for c in by_key.values() if c.key != "C7")


def test_extracted_lines_are_verbatim_and_in_order(repo):
    records = evidence.load(repo[1])
    for claim in evidence.claims(records):
        for block in claim.blocks:
            source = block.record.lines
            position = 0
            for line in block.lines:
                position = source.index(line, position) + 1  # raises if retyped


def test_live_is_preferred_and_replay_used_when_live_was_skipped(repo):
    by_key = {c.key: c for c in evidence.claims(evidence.load(repo[1]))}
    c3_lines = "\n".join(by_key["C3"].blocks[1].lines)
    assert by_key["C3"].blocks[1].where.endswith("› Live")
    assert " replay |" not in c3_lines
    assert by_key["C4"].blocks[1].where.endswith("› Stress set: replay")


def test_the_pack_and_the_readme_block(repo):
    code, out = run(repo)
    assert code == 0
    pack = out.read_text(encoding="utf-8")
    for title in (
        "C1 Coverage",
        "C2 Accuracy, hand-written keys",
        "C3 Accuracy at scale",
        "C4 Failure modes",
        "C5 Representation loss",
        "C6 Overhead",
        "C7 Start-up",
        "C8 Throughput model",
    ):
        assert f"\n## {title}\n" in pack
    assert "**OpenLineage baseline, measured**" in pack  # headings become labels
    assert "\n### OpenLineage baseline" not in pack
    readme = repo[2].read_text(encoding="utf-8")
    assert readme.startswith("# Title\n\nBefore.\n\n" + evidence.START)
    assert readme.endswith(evidence.END + "\n\nAfter.\n")
    assert "old" not in readme
    block = readme.split(evidence.START)[1].split(evidence.END)[0]
    rows = [line for line in block.splitlines() if line.startswith("| [C")]
    assert 3 <= len(rows) <= 5
    assert "T1 inconclusive" in block  # the owner's newer verdict, copied
    assert "+50.0 [+40.0, +60.0]" in block and "2450.0" in block


def test_running_twice_gives_identical_bytes_and_check_passes(repo):
    _code, out = run(repo)
    first = (out.read_bytes(), repo[2].read_bytes())
    _code, out = run(repo)
    assert (out.read_bytes(), repo[2].read_bytes()) == first
    assert run(repo, "--check")[0] == 0
    out.write_text("stale\n", encoding="utf-8")
    assert run(repo, "--check")[0] == 1


def test_a_missing_claim_is_said_not_invented(repo):
    _tmp, results, _readme = repo
    for path in results.glob("*.md"):
        path.unlink()
    (results / "P5-empty.md").write_text("# empty\n", encoding="utf-8")
    pack = evidence.render(evidence.load(results))
    assert pack.count("*No committed record contains this evidence yet.*") == 8


def test_a_readme_without_markers_is_refused():
    with pytest.raises(ValueError, match="evidence:summary:start"):
        evidence.rewrite_readme("# no block\n", ["x"])


def test_crlf_records_extract_the_same(repo):
    _tmp, results, _readme = repo
    before = evidence.render(evidence.load(results))
    for path in results.glob("*.md"):
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert evidence.render(evidence.load(results)) == before


def test_slugs_are_github_anchors():
    assert (
        evidence.slug("C2 Accuracy, hand-written keys")
        == "c2-accuracy-hand-written-keys"
    )
    assert evidence.slug("C1 Coverage") == "c1-coverage"


def test_the_committed_pack_and_readme_block_are_up_to_date():
    """docs/paper/evidence.md and the README block are what the script writes
    from the committed records (CRLF-safe: both sides are read as text)."""
    assert evidence.main(["--check"]) == 0


def test_a_single_run_renders_a_fixed_cost_record_the_pack_picks_up(tmp_path, repo):
    import render

    fixture = pathlib.Path(__file__).parent / "data" / "render_p51_fixture.json"
    record = repo[1] / "P5-local-final-fixed-cost.md"
    assert render.main(["--fixed-cost", str(fixture), str(record)]) == 0
    text = record.read_text(encoding="utf-8")
    assert text.startswith("# Fixed cost per call: `fixture-p51`\n")
    assert "\n### The fixed cost per call and the < 2% throughput target\n" in text
    assert "From the run's implied added µs per call" in text
    # The comparison's wording is unchanged.
    import json

    data = json.loads(fixture.read_text(encoding="utf-8"))
    assert "target (after)" in render.render_comparison(data, data)
    # The fixture run started 2026-01-02, after the sandbox fixture record.
    (c8,) = [c for c in evidence.claims(evidence.load(repo[1])) if c.key == "C8"]
    assert c8.blocks[0].record.name == "P5-local-final-fixed-cost.md"
    assert c8.blocks[0].record.owner
