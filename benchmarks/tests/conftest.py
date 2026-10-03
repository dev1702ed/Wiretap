"""Benchmark unit tests: no Postgres, no Kafka, no live extras.

benchmarks/ is not a package. Its stage directories (live, overhead,
adversarial) are imported as namespace packages from benchmarks/, and the
ground-truth modules (harness, score) by top-level name, as score.py itself
does. run.py sets up the same path.
"""

import pathlib
import sys

BENCHMARKS = pathlib.Path(__file__).resolve().parents[1]
for path in (BENCHMARKS / "ground_truth", BENCHMARKS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
