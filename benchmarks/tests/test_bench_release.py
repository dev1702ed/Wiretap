"""Release metadata (P5.2, C1): one version everywhere, the changelog, the
citation file, and binary figures."""

import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
VERSION = "0.1.0"
PYPROJECTS = ("sdk-python", "backend", "bridges/openlineage")


def pyproject_version(directory: str) -> str:
    text = (ROOT / directory / "pyproject.toml").read_text(encoding="utf-8")
    (version,) = re.findall(r'^version = "([^"]+)"$', text, re.MULTILINE)
    return version


def module_version(path: str) -> str:
    """__version__ from the source file, not from installed metadata."""
    text = (ROOT / path).read_text(encoding="utf-8")
    (version,) = re.findall(r'^__version__ = "([^"]+)"$', text, re.MULTILINE)
    return version


def test_the_version_is_0_1_0_and_all_four_agree():
    versions = {d: pyproject_version(d) for d in PYPROJECTS}
    versions["dcp.__version__"] = module_version("sdk-python/dcp/__init__.py")
    versions["dcp_openlineage.__version__"] = module_version(
        "bridges/openlineage/dcp_openlineage/__init__.py"
    )
    assert versions == dict.fromkeys(versions, VERSION)
    if importlib.util.find_spec("dcp"):
        import dcp

        assert dcp.__version__ == VERSION


def test_the_changelog_has_a_0_1_0_entry_for_every_phase():
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## [{VERSION}]" in text
    for phase in ("P0", "P1", "P2", "P3", "P4", "P5", "P5.1", "P5.2"):
        assert f"- **{phase} — " in text, phase
    for report in ("P3", "P4", "P5", "P5.1", "P5.2"):
        assert f"(docs/results/{report}.md)" in text, report


def test_the_citation_file_is_cff_1_2_with_no_placeholder():
    text = (ROOT / "CITATION.cff").read_text(encoding="utf-8")
    fields = dict(re.findall(r"^([a-z-]+): (.+)$", text, re.MULTILINE))
    assert fields["cff-version"] == "1.2.0"
    assert fields["version"] == VERSION
    assert fields["license"] == "Apache-2.0"
    assert fields["repository-code"] == '"https://github.com/dev1702ed/Wiretap"'
    assert re.fullmatch(r'"\d{4}-\d{2}-\d{2}"', fields["date-released"])
    assert fields["title"].startswith('"DCP')
    authors = text.split("authors:", 1)[1]
    assert "family-names:" in authors and "given-names:" in authors
    # The owner filled in the author (docs/RUNBOOK.md, step 9): no placeholder remains.
    assert not re.findall(r"REPLACE_[A-Z_]+", text)


def test_figures_are_committed_as_binary():
    lines = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert "*.png binary" in lines and "*.pdf binary" in lines
    # The owner's original line, unchanged (P5 rule 5).
    assert "bridges/openlineage/schema/OpenLineage.json -text" in lines
