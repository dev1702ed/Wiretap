"""Dataset identity: deterministic, lossless normalisation only.

See docs/decisions/identity.md. A false merge invents lineage, so anything
not provably the same dataset stays a separate node.
"""

import json
import pathlib

import pytest
from app.identity import resolve

GROUND_TRUTH = pathlib.Path(__file__).parents[2] / "benchmarks" / "ground_truth"


def test_ground_truth_identities_come_through_unchanged():
    keys = [
        json.loads(p.read_text()) for p in GROUND_TRUTH.glob("*/expected_graph.json")
    ]
    datasets = [d for key in keys for d in key["datasets"].values()]
    assert datasets
    for d in datasets:
        assert resolve(d["namespace"], d["name"]) == (d["namespace"], d["name"])


@pytest.mark.parametrize(
    "namespace,expected",
    [
        (" postgres://localhost:5432 ", "postgres://localhost:5432"),
        ("POSTGRES://localhost:5432", "postgres://localhost:5432"),
        ("postgres://Prod-DB.Internal:5432", "postgres://prod-db.internal:5432"),
        ("Kafka://Broker-1:9092", "kafka://broker-1:9092"),
        ("postgres://[FE80::1]:5432", "postgres://[fe80::1]:5432"),
    ],
)
def test_scheme_and_host_are_lowercased_and_trimmed(namespace, expected):
    assert resolve(namespace, "dcp.public.orders") == (expected, "dcp.public.orders")


@pytest.mark.parametrize(
    "namespace,expected",
    [
        ("postgres://User@HOST:5432", "postgres://User@host:5432"),  # userinfo kept
        ("postgres://HOST:5432/Path", "postgres://host:5432/Path"),
        ("postgres://HOST:5432?Opt=X", "postgres://host:5432?Opt=X"),
        ("Not-A-URI", "Not-A-URI"),
    ],
)
def test_only_scheme_and_host_change(namespace, expected):
    assert resolve(namespace, "t") == (expected, "t")


def test_names_are_trimmed_but_never_case_folded():
    """Postgres quoted identifiers and Kafka topics are case-sensitive."""
    assert resolve("kafka://b:9092", " Orders ") == ("kafka://b:9092", "Orders")
    assert (
        resolve("postgres://h:5432", 'dcp.public."MixedCase"')[1]
        == 'dcp.public."MixedCase"'
    )


@pytest.mark.parametrize(
    "a,b",
    [
        ("postgres://localhost:5432", "postgres://127.0.0.1:5432"),
        ("postgres://localhost:5432", "postgres://localhost"),
        ("postgres://prod-db:5432", "postgres://prod-db.internal:5432"),
        ("kafka://b1:9092", "kafka://b2:9092"),
    ],
)
def test_distinct_spellings_are_never_merged(a, b):
    assert resolve(a, "t") != resolve(b, "t")


def test_is_idempotent():
    once = resolve("  POSTGRES://LocalHost:5432 ", " dcp.public.orders ")
    assert resolve(*once) == once
