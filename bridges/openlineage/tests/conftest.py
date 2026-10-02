"""Shared fixtures: a DCP event builder, and validators for the vendored
OpenLineage schema and the dcp run facet schema."""

import importlib.util
import json
import pathlib
import sys

import jsonschema
import pytest

ROOT = pathlib.Path(__file__).parents[1]
OL_SCHEMA = json.loads((ROOT / "schema" / "OpenLineage.json").read_text())
FACET_SCHEMA = json.loads((ROOT / "facets" / "DcpRunFacet.json").read_text())
_ol = jsonschema.Draft202012Validator(
    OL_SCHEMA, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
)
_facet = jsonschema.Draft202012Validator(
    FACET_SCHEMA, format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER
)


def validate_all(ol_events) -> None:
    """Every event against the official spec; every dcp facet against ours."""
    for event in ol_events:
        _ol.validate(event)
        facet = event["run"].get("facets", {}).get("dcp")
        if facet is not None:
            _facet.validate(facet)


@pytest.fixture
def validate():
    return validate_all


@pytest.fixture(scope="session")
def harness():
    """benchmarks/ground_truth/harness.py: real capture output for each workload."""
    pytest.importorskip("dcp")
    path = ROOT.parents[1] / "benchmarks" / "ground_truth" / "harness.py"
    spec = importlib.util.spec_from_file_location("ground_truth_harness", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_event(
    edge_id,
    op,
    dataset,
    job="job.py",
    parent=(),
    trace_id="11111111-1111-4111-8111-111111111111",
    host="host-a",
    pid=1,
    ts="2026-09-16T02:11:04+00:00",
):
    return {
        "dcp_version": "0.1",
        "trace_id": trace_id,
        "edge_id": edge_id,
        "parent": list(parent),
        "op": op,
        "dataset": {"namespace": dataset[0], "name": dataset[1]},
        "job": {"name": job, "host": host, "pid": pid},
        "ts": ts,
    }


@pytest.fixture
def ev():
    return make_event
