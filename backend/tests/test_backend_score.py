"""score.py runs as documented and scores every level of every workload.

The numbers themselves are pinned by sdk-python/tests/test_ground_truth.py,
which replays through the same harness. Needs the SDK as well as the backend.
"""

import json
import pathlib
import subprocess
import sys

import pytest

pytest.importorskip("dcp")

GROUND_TRUTH = pathlib.Path(__file__).parents[2] / "benchmarks" / "ground_truth"


def test_score_runs_and_covers_every_level():
    result = subprocess.run(
        [sys.executable, str(GROUND_TRUTH / "score.py")],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    for key_path in sorted(GROUND_TRUTH.glob("*/expected_graph.json")):
        key = json.loads(key_path.read_text())
        assert f"== {key['workload']}" in result.stdout
        for p in key["provenance"]:
            assert f"upstream({p['dataset']}) run-level" in result.stdout
            assert f"upstream({p['dataset']}) dataset-level baseline" in result.stdout
    for level in ("nodes", "dataset edges", "run edges"):
        assert level in result.stdout
