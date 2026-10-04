"""score.py runs as documented and scores every level of every workload.

The numbers themselves are pinned by sdk-python/tests/test_ground_truth.py,
which replays through the same harness, and by the bridge's own tests for the
OpenLineage section. Needs the SDK as well as the backend; score.py finds the
bridge in bridges/openlineage if it is not installed.
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
            assert f"openlineage provenance({p['dataset']})" in result.stdout
            assert f"openlineage + dcp facet provenance({p['dataset']})" in result.stdout
            assert f"openlineage (per process) provenance({p['dataset']})" in result.stdout
        assert f"-- {key['workload']}: OpenLineage translation" in result.stdout
        assert (
            f"-- {key['workload']}: OpenLineage translation, one run per process" in result.stdout
        )
    for level in ("nodes", "dataset edges", "run edges", "openlineage dataset edges"):
        assert level in result.stdout
    assert "openlineage (per process) dataset edges" in result.stdout


def test_replay_output_is_pinned():
    """score.py's replay output, byte for byte (P5).

    The event source is pluggable (replay or live); the refactor that made it
    so must not change a byte of the replay output. The expected file is
    checked out without line-ending conversion (.gitattributes: -text), and
    universal newlines on stdout make the comparison the same on Windows.
    A new or changed answer key changes this output: regenerate the file from
    score.py's stdout (UTF-8, LF line endings; Windows PowerShell 5.1's `>`
    writes UTF-16, so don't use it) and review the diff.
    """
    result = subprocess.run(
        [sys.executable, str(GROUND_TRUTH / "score.py")],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    expected = (pathlib.Path(__file__).parent / "data" / "score_replay.txt").read_bytes()
    assert result.stdout == expected.decode("utf-8")
