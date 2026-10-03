"""stats.py on inputs with known answers."""

import random

import pytest
from overhead import stats


def test_percentile_interpolates_linearly():
    assert stats.percentile([1, 2, 3, 4], 50) == 2.5
    assert stats.percentile([4, 1, 3, 2], 0) == 1
    assert stats.percentile([4, 1, 3, 2], 100) == 4
    assert stats.percentile(list(range(101)), 99) == 99
    assert stats.percentile(list(range(1001)), 99.9) == pytest.approx(999)
    assert stats.percentile([7], 99.9) == 7


def test_percentile_rejects_bad_input():
    with pytest.raises(ValueError):
        stats.percentile([], 50)
    with pytest.raises(ValueError):
        stats.percentile([1], 101)


def test_summarize_scales():
    s = stats.summarize([1000, 2000, 3000, 4000, 5000], scale=1000)
    assert (s["p50"], s["max"], s["n"]) == (3.0, 5.0, 5)
    assert set(s) == {"p50", "p95", "p99", "p99.9", "max", "n"}


def test_pairing_removes_round_to_round_drift():
    """Instrumented = base + 2 in every round, while base drifts wildly.

    A paired difference is exactly 2 with a zero-width interval; an unpaired
    comparison of the same numbers would be dominated by the drift.
    """
    rng = random.Random(1)
    base = [rng.uniform(100, 10_000) for _ in range(10)]
    instrumented = [b + 2 for b in base]
    result = stats.paired_difference(base, instrumented)
    assert result["estimate"] == pytest.approx(2)
    assert result["low"] == pytest.approx(2)
    assert result["high"] == pytest.approx(2)


def test_bootstrap_interval_of_a_known_sample():
    """Mean of 1..9 is 5; the bootstrap interval brackets it, inside the sample's range."""
    result = stats.bootstrap_mean_ci(range(1, 10))
    assert result["estimate"] == 5
    assert 1 < result["low"] < 5 < result["high"] < 9
    # Standard error of the mean is sqrt(60/9)/3 ≈ 0.861; a 95% interval is about ±1.7.
    assert result["high"] - result["low"] == pytest.approx(3.4, abs=0.5)


def test_bootstrap_is_reproducible_and_seeded():
    first = stats.bootstrap_mean_ci([1, 5, 2, 8, 3])
    assert stats.bootstrap_mean_ci([1, 5, 2, 8, 3]) == first
    assert stats.bootstrap_mean_ci([1, 5, 2, 8, 3], seed=7) != first
    assert (first["resamples"], first["seed"]) == (10_000, stats.BOOTSTRAP_SEED)


def test_percent_change_is_paired():
    result = stats.paired_percent_change([100, 200, 400], [99, 198, 396])
    assert result["estimate"] == pytest.approx(-1)
    assert result["low"] == pytest.approx(-1) and result["high"] == pytest.approx(-1)


def test_pairs_must_match():
    with pytest.raises(ValueError):
        stats.paired_difference([1, 2], [1])


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        (100, 900, "met"),
        (1000, 3000, "not met"),
        (1500, 3000, "not met"),
        (500, 1500, "inconclusive"),
        (-50, 999, "met"),
    ],
)
def test_latency_verdicts(low, high, expected):
    assert stats.latency_verdict({"low": low, "high": high}) == expected


@pytest.mark.parametrize(
    ("low", "high", "expected"),
    [
        (-1.0, 0.5, "met"),  # loss at most 1%
        (-5.0, -3.0, "not met"),  # loss 3-5%
        (-3.0, -1.0, "inconclusive"),  # loss 1-3%
        (1.0, 2.0, "met"),  # a gain
    ],
)
def test_throughput_verdicts(low, high, expected):
    assert stats.throughput_verdict({"low": low, "high": high}) == expected
