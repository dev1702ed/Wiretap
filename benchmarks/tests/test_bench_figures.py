"""The paper's figures (P5.2, C5): from raw results JSON (fixtures here),
deterministic, labelled with their source, and the record fallback parses the
same numbers the JSON holds."""

import json
import pathlib

import figures
import pytest
import render

pytest.importorskip("matplotlib")

FIXTURE = pathlib.Path(__file__).parent / "data" / "render_p51_fixture.json"


def aggregate_rows(scale: float) -> list[dict]:
    rows = []
    for method in figures.METHOD_ORDER:
        for level in ("dataset edges", "provenance"):
            rows.append({"method": method, "level": level, "precision": 0.5 * scale,
                         "recall": 1.0, "hits": 1, "found": 2, "expected": 1})  # fmt: skip
    return rows


def scale_results(label="p52-fixture", started="2026-01-03T00:00:00+00:00") -> dict:
    def summary(scale):
        return {"seeds": {"names": ["a", "b"], "aggregate": aggregate_rows(scale)}}

    return {
        "label": label,
        "environment": {"git_commit": "f" * 40, "timestamp_utc": started},
        "scale": {
            "replay": {"summary": summary(1.0)},
            "live": {"summary": summary(1.5)},
            "stress": {
                "replay": {"summary": summary(1.2)},
                "live": {"skipped": "no services"},
            },
        },
    }


@pytest.fixture
def data(tmp_path):
    root = tmp_path / "data"
    (root / "p52-fixture").mkdir(parents=True)
    (root / "p52-fixture" / "results.json").write_text(json.dumps(scale_results()))
    (root / "older").mkdir()
    (root / "older" / "results.json").write_text(
        json.dumps(scale_results("older", "2025-01-01T00:00:00+00:00"))
    )
    return root


def test_live_is_used_when_it_ran_and_replay_when_it_did_not():
    results = scale_results()
    assert figures.accuracy(results, "scale")[0]["precision"] == 0.75  # live
    assert figures.accuracy(results, "stress")[0]["precision"] == 0.6  # replay


def test_all_five_figures_from_fixture_json(tmp_path, data):
    out = tmp_path / "figures"
    code = figures.main(
        ["--data", str(data), "--overhead", str(FIXTURE), "--out", str(out)]
    )
    assert code == 0
    names = sorted(p.name for p in out.iterdir())
    assert names == sorted(
        f"{f}.{ext}"
        for f in ("F1-scale-accuracy", "F2-stress-accuracy", "F3-added-p99",
                  "F4-fixed-cost", "F5-startup")
        for ext in ("pdf", "png")
    )  # fmt: skip
    for path in out.iterdir():
        content = path.read_bytes()
        assert b"CreationDate" not in content and b"Matplotlib" not in content, (
            path.name
        )
        assert content.startswith(b"%PDF" if path.suffix == ".pdf" else b"\x89PNG")


def test_running_twice_gives_identical_bytes(tmp_path, data):
    a, b = tmp_path / "a", tmp_path / "b"
    for out in (a, b):
        figures.main(
            ["--data", str(data), "--overhead", str(FIXTURE), "--out", str(out)]
        )
    for path in a.iterdir():
        assert path.read_bytes() == (b / path.name).read_bytes(), path.name


def test_the_newest_committed_run_with_the_stress_group_is_the_default(data):
    path, results = figures.newest_with(
        figures.committed_runs(data), lambda r: "stress" in r.get("scale", {})
    )
    assert results["label"] == "p52-fixture"
    label = figures.source_label(path, results)
    assert "run `p52-fixture`" in label and "the sandbox" in label
    assert "the owner's machine" in figures.source_label(
        path, dict(results, label="local-final")
    )


def test_the_record_fallback_parses_what_the_json_holds(tmp_path):
    """Render the fixture JSON as a record, parse it back: the same numbers,
    to the record's precision (0.1 µs)."""
    results = json.loads(FIXTURE.read_text(encoding="utf-8"))
    from_json = figures.overhead_from_results(results)
    lines = render.render(results).split("\n")
    from_record = figures.overhead_from_record("P5-fixture.md", lines)
    assert set(from_record["tiers"]) == set(from_json["tiers"])
    for tier, configs in from_json["tiers"].items():
        for config, v in configs.items():
            got = from_record["tiers"][tier][config]
            for key in ("added_p99_us", "implied_added_us"):
                for part in ("estimate", "low", "high"):
                    assert got[key][part] == pytest.approx(v[key][part], abs=0.051)
    for command, s in from_json["startup"].items():
        assert from_record["startup"][command]["p50"] == pytest.approx(
            s["p50"], abs=0.051
        )


def test_without_raw_overhead_json_the_newest_record_is_parsed_and_labelled(
    tmp_path, data
):
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    (results_dir / "P5-fixture.md").write_text(render.render(fixture), encoding="utf-8")
    overhead, label = figures.overhead_source(data, results_dir)
    assert "P5-fixture.md (rendered record, parsed by code" in label
    assert "T1 point read" in overhead["tiers"]


def test_the_committed_figures_exist_for_f1_and_f2():
    out = figures.OUT
    for name in ("F1-scale-accuracy", "F2-stress-accuracy", "F3-added-p99",
                 "F4-fixed-cost", "F5-startup"):  # fmt: skip
        for ext in ("pdf", "png"):
            assert (out / f"{name}.{ext}").stat().st_size > 1000
