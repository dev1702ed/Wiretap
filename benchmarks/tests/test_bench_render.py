"""The renderer, from a fixture JSON, byte for byte.

data/render_fixture.json is a SYNTHETIC results file: trimmed from a trial run,
with a made-up environment, a failed stage, a skipped stage and a broken
interpreter, so every branch of the renderer is exercised. Its numbers are not
results. The expected markdown files are checked out without line-ending
conversion (.gitattributes: -text), so this passes on a Windows checkout too.

To regenerate after an intended renderer change, run this file with
REGENERATE=1 and review the diff.
"""

import copy
import json
import os
import pathlib

import pytest
import render

DATA = pathlib.Path(__file__).parent / "data"
FIXTURE = DATA / "render_fixture.json"
EXPECTED = DATA / "render_expected.md"
EXPECTED_COMPARISON = DATA / "render_comparison_expected.md"


def fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def after(before: dict) -> dict:
    """A deterministic 'after' run for the comparison: every capture time halved."""
    out = copy.deepcopy(before)
    out["label"] = "fixture-after"
    for py in out["cpu"]["pythons"]:
        for tier in py.get("tiers", {}).values():
            tier["capture_us"] = {k: v / 2 for k, v in tier["capture_us"].items()}
    return out


def check(text: str, expected: pathlib.Path) -> None:
    if os.environ.get("REGENERATE") == "1":
        expected.write_bytes(text.encode("utf-8"))
    assert text == expected.read_bytes().decode("utf-8")


def test_render_matches_the_expected_markdown():
    check(render.render(fixture()), EXPECTED)


def test_comparison_matches_the_expected_markdown():
    before = fixture()
    check(render.render_comparison(before, after(before)), EXPECTED_COMPARISON)


def test_render_is_deterministic():
    assert render.render(fixture()) == render.render(fixture())


def test_every_section_and_branch_is_present():
    text = render.render(fixture())
    for heading in (
        "## Environment",
        "## Stages",
        "## Ground truth: replay",
        "## Ground truth: live",
        "## Adversarial",
        "## Overhead: CPU microbenchmark (4a)",
        "## Overhead: live (4b)",
        "## Stage 5 trigger (parse cache)",
    ):
        assert heading in text
    assert render.CI_NOTE in text  # environment.ci is true in the fixture
    assert "### `overhead` failed" in text and "synthetic failure" in text
    assert "| cpu | skipped |" in text and "synthetic reason" in text
    assert "`/synthetic/broken-python`: failed" in text


def test_no_ci_note_off_ci():
    results = fixture()
    results["environment"]["ci"] = False
    assert render.CI_NOTE not in render.render(results)


def test_trigger_reads_the_numbers():
    results = fixture()
    fired = render.stage5_trigger(results)
    assert any(line.startswith("4a,") for line in fired)
    for py in results["cpu"]["pythons"]:
        for tier in py.get("tiers", {}).values():
            tier["capture_us"]["p99"] = 1.0
    for tier in results["overhead"]["postgres"]["tiers"].values():
        tier["versus_base"]["file"]["added_p99_us"]["estimate"] = 1.0
    assert render.stage5_trigger(results) == []


@pytest.mark.parametrize(
    ("value", "text"), [(None, "n/a"), (1.25, "1.2"), (1234.56, "1234.6")]
)
def test_number_formats(value, text):
    assert render.us(value) == text


# P5.1: the L tiers, ablations, implied cost, attribution, profile, pins.
# data/render_p51_fixture.json is SYNTHETIC in the same way: trimmed from a
# quick trial run, with a made-up environment and a fabricated pin mismatch.
FIXTURE_P51 = DATA / "render_p51_fixture.json"
EXPECTED_P51 = DATA / "render_p51_expected.md"
EXPECTED_P51_COMPARISON = DATA / "render_p51_comparison_expected.md"


def fixture_p51() -> dict:
    return json.loads(FIXTURE_P51.read_text(encoding="utf-8"))


def after_p51(before: dict) -> dict:
    """A deterministic 'after' for the P5.1 comparison: capture halved, every
    added and implied cost halved, start-up halved, one tier left out."""
    out = after(before)
    out["label"] = "fixture-p51-after"

    def halve(result):
        return {
            k: (v / 2 if k in ("estimate", "low", "high") else v)
            for k, v in result.items()
        }

    for tier in out["overhead"]["postgres"]["tiers"].values():
        for v in tier["versus_base"].values():
            for key in ("added_p50_us", "added_p99_us", "implied_added_us"):
                v[key] = halve(v[key])
        for row in tier["attribution"]:
            row["p50_us"], row["implied_us"] = (
                halve(row["p50_us"]),
                halve(row["implied_us"]),
            )
    for py in out["cpu"]["pythons"]:
        for tier in py["tiers"].values():
            tier["normalize_us"] = {k: 1.0 for k in tier["capture_us"]}
    for value in out["overhead"]["startup"]["ms"].values():
        for k in ("p50", "p95"):
            value[k] /= 2
    del out["overhead"]["postgres"]["tiers"]["T2"]
    return out


def test_p51_render_matches_the_expected_markdown():
    check(render.render(fixture_p51()), EXPECTED_P51)


def test_p51_comparison_matches_the_expected_markdown():
    before = fixture_p51()
    text = render.render_comparison(before, after_p51(before), "P5.1: before and after")
    check(text, EXPECTED_P51_COMPARISON)


def test_p51_sections_are_present_and_disclosed():
    text = render.render(fixture_p51())
    assert render.P51_TIERS_NOTE in text and render.P51_CONFIGS_NOTE in text
    assert "### L1 point read, literal (added in P5.1)" in text
    assert "Implied added µs/call [95% CI]" in text
    assert "### Attribution of the added cost (added in P5.1)" in text
    assert "### Profiling round (added in P5.1)" in text and render.PROFILE_NOTE in text
    assert "none by design (capture off)" in text
    assert "**1 of 3 differ from the pins**" in text


def test_the_p5_fixture_renders_without_any_p51_section():
    """Results from before P5.1 (no implied cost, no ablations) render as they did."""
    text = render.render(fixture())
    for marker in (
        "added in P5.1",
        "Implied",
        "Attribution",
        "Profiling round",
        "Pinned",
    ):
        assert marker not in text


def test_the_normalisation_columns_appear_only_when_measured():
    results = fixture_p51()
    assert "normalise p50" not in render.render(results)
    for py in results["cpu"]["pythons"]:
        for tier in py["tiers"].values():
            tier["normalize_us"] = {"p50": 2.5, "p99": 4.0}
    text = render.render(results)
    assert "| classify p99 | normalise p50 | normalise p99 |" in text
    assert render.NORMALIZE_NOTE in text
