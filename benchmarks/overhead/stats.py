"""Statistics for the overhead benchmark. P5. Stdlib only.

- Percentiles use linear interpolation between closest ranks (numpy's default
  "linear" method), so p50 of [1, 2, 3, 4] is 2.5.
- Added latency and throughput delta are PAIRED by round: round r of a
  configuration is compared with round r of `base`, which ran next to it.
  Pairing cancels drift that affects both (thermal state, a noisy neighbour).
- Confidence intervals are percentile bootstraps over rounds: resample the
  per-round differences with replacement, take the mean, repeat, read off the
  2.5th and 97.5th percentiles. The seed is fixed, so a result re-renders
  identically.
- A verdict compares the whole interval with the target: "met" if it lies
  below, "not met" if it lies at or above, "inconclusive" if it straddles it.
"""

import math
import random
from statistics import fmean

PERCENTILES = (50, 95, 99, 99.9)
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261003
CONFIDENCE = 0.95


def percentile(values, q: float) -> float:
    """The q-th percentile (0-100) of `values`, linearly interpolated."""
    if not values:
        raise ValueError("percentile of no values")
    if not 0 <= q <= 100:
        raise ValueError(f"percentile out of range: {q}")
    ordered = sorted(values)
    rank = (len(ordered) - 1) * q / 100
    low = math.floor(rank)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def summarize(values, scale: float = 1.0) -> dict:
    """p50, p95, p99, p99.9 and max of `values`, each divided by `scale`."""
    ordered = sorted(values)
    out = {f"p{q:g}": percentile(ordered, q) / scale for q in PERCENTILES}
    out["max"] = ordered[-1] / scale
    out["n"] = len(ordered)
    return out


def bootstrap_mean_ci(
    differences,
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = BOOTSTRAP_SEED,
    confidence: float = CONFIDENCE,
) -> dict:
    """Mean of `differences` and its percentile-bootstrap confidence interval."""
    diffs = list(differences)
    if not diffs:
        raise ValueError("bootstrap of no differences")
    rng = random.Random(seed)
    n = len(diffs)
    means = [fmean(rng.choices(diffs, k=n)) for _ in range(resamples)]
    tail = (1 - confidence) / 2 * 100
    return {
        "estimate": fmean(diffs),
        "low": percentile(means, tail),
        "high": percentile(means, 100 - tail),
        "rounds": n,
        "resamples": resamples,
        "seed": seed,
    }


def paired_difference(base, instrumented, **kwargs) -> dict:
    """instrumented[r] - base[r], paired by round, with a bootstrap CI of the mean."""
    if len(base) != len(instrumented):
        raise ValueError("paired rounds must match one to one")
    return bootstrap_mean_ci(
        [i - b for b, i in zip(base, instrumented, strict=True)], **kwargs
    )


def paired_percent_change(base, instrumented, **kwargs) -> dict:
    """100 * (instrumented[r] - base[r]) / base[r], paired by round, with a CI."""
    if len(base) != len(instrumented):
        raise ValueError("paired rounds must match one to one")
    changes = [100 * (i - b) / b for b, i in zip(base, instrumented, strict=True)]
    return bootstrap_mean_ci(changes, **kwargs)


def verdict(low: float, high: float, limit: float) -> str:
    """Against `limit` (lower is better): met, not met, or inconclusive."""
    if high < limit:
        return "met"
    if low >= limit:
        return "not met"
    return "inconclusive"


def latency_verdict(added_p99_us: dict, limit_us: float = 1000.0) -> str:
    """< 1 ms (1,000 µs) p99 added latency."""
    return verdict(added_p99_us["low"], added_p99_us["high"], limit_us)


def throughput_verdict(change_pct: dict, limit_pct: float = 2.0) -> str:
    """< 2% throughput loss. A loss is a negative change, so the interval flips."""
    return verdict(-change_pct["high"], -change_pct["low"], limit_pct)
