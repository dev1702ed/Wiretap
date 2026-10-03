"""The baseline check's stub and preconditions. No infrastructure."""

import json
import pathlib
import urllib.request

import pytest
from adversarial import baseline_check
from live import generate, run_live


def post(url: str, body: dict) -> int:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return response.status


def test_stub_counts_every_request_on_any_path():
    stub = baseline_check.Stub()
    try:
        assert post(stub.url + "/api/v1/lineage", {"eventType": "START"}) == 200
        assert post(stub.url + "/anything", {"eventType": "COMPLETE"}) == 200
        with urllib.request.urlopen(stub.url + "/x", timeout=10) as response:
            assert response.status == 200
    finally:
        stub.close()
    assert [(r["method"], r["path"], r["eventType"]) for r in stub.requests] == [
        ("POST", "/api/v1/lineage", "START"),
        ("POST", "/anything", "COMPLETE"),
        ("GET", "/x", None),
    ]


def test_check_refuses_to_run_without_the_services(monkeypatch, tmp_path):
    monkeypatch.setattr(run_live, "unavailable", lambda: "PostgreSQL is not reachable")
    with pytest.raises(run_live.LiveUnavailable, match="not reachable"):
        baseline_check.run(tmp_path)


def test_check_covers_cases_1_and_2():
    assert baseline_check.WORKLOADS == ("dark_zone", "notebook")


def test_the_positive_control_declares_lineage_by_hand():
    """manual_emission.py is OpenLineage code; the programs under test are not."""
    source = baseline_check.MANUAL.read_text(encoding="utf-8")
    assert "from openlineage.client import OpenLineageClient" in source
    assert 'InputDataset("postgres://localhost:5432", "dcp.public.orders")' in source
    assert generate.dcp_code_in(source) == []


def test_the_baseline_programs_never_mention_openlineage():
    """Installation alone is what is under test: the programs make no OpenLineage call."""
    from harness import load

    for name in baseline_check.WORKLOADS:
        for index, process in enumerate(load(name)["processes"]):
            source = generate.script_source(name, process, f"g{index}")
            assert "openlineage" not in source.lower()


def test_baseline_md_names_the_vendored_tag():
    text = (pathlib.Path(baseline_check.__file__).parent / "BASELINE.md").read_text(
        encoding="utf-8"
    )
    assert "tag `1.53.0`" in text
    assert "tree/1.53.0/integration/spark" in text
