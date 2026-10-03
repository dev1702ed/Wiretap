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
