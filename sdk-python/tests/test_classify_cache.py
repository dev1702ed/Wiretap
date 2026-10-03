"""The parse cache (P5 Stage 5): same results, bounded, and immutable.

The cache must not change any output, so every query here is classified both
through the cache and directly, and the two must agree. The ground truth and
the pinned replay output (backend/tests/test_backend_score.py) cover the rest.
"""

import json
import pathlib

import pytest

from dcp.interceptors import postgres

ROOT = pathlib.Path(__file__).parents[2]

CORPUS = [
    "SELECT id FROM orders",
    "SELECT id, total FROM orders WHERE id = %s",
    "SELECT o.id FROM orders o JOIN summary s ON o.id = s.id",
    "INSERT INTO summary SELECT id FROM orders",
    "INSERT INTO summary VALUES (%s, %s)",
    "CREATE TABLE derived AS SELECT id FROM orders",
    "UPDATE summary SET total = 0 WHERE id IN (SELECT id FROM orders)",
    "DELETE FROM summary WHERE id = 1",
    "SELECT id FROM Sales.Orders",
    'SELECT id FROM "Orders"',
    "SELECT id FROM dcp.public.orders",
    "WITH x AS (SELECT id FROM orders) INSERT INTO summary SELECT id, 1 FROM x",
    "CREATE TABLE IF NOT EXISTS orders (id int, total numeric)",
    "DROP TABLE orders",
    "BEGIN",
    "this is not sql at all ((",
    "",
]


def key_queries() -> list[str]:
    queries = []
    for path in sorted((ROOT / "benchmarks" / "ground_truth").glob("*/expected_graph.json")):
        for process in json.loads(path.read_text(encoding="utf-8"))["processes"]:
            queries += [step["sql"] for step in process["steps"] if "sql" in step]
    return queries


@pytest.fixture(autouse=True)
def empty_cache():
    postgres._classify_parts_cached.cache_clear()
    yield
    postgres._classify_parts_cached.cache_clear()


@pytest.mark.parametrize("query", CORPUS + key_queries())
def test_cached_and_uncached_agree(query):
    direct = postgres._classify_parts_uncached(query)
    assert postgres._classify_parts(query) == direct  # miss: computed and stored
    assert postgres._classify_parts(query) == direct  # hit: served from the cache


def test_repeated_text_is_a_hit():
    for _ in range(5):
        postgres._classify_parts("SELECT id FROM orders WHERE id = %s")
    info = postgres._classify_parts_cached.cache_info()
    assert (info.misses, info.hits, info.currsize) == (1, 4, 1)


def test_keyed_on_exact_text():
    postgres._classify_parts("SELECT id FROM orders")
    postgres._classify_parts("SELECT id FROM orders ")
    postgres._classify_parts("select id from orders")
    assert postgres._classify_parts_cached.cache_info().currsize == 3


def test_bounded_in_entries():
    for i in range(postgres.CLASSIFY_CACHE_SIZE + 100):
        postgres._classify_parts(f"SELECT id FROM orders WHERE id = {i}")
    info = postgres._classify_parts_cached.cache_info()
    assert info.maxsize == postgres.CLASSIFY_CACHE_SIZE
    assert info.currsize == postgres.CLASSIFY_CACHE_SIZE


def test_very_long_texts_are_never_held():
    rows = ", ".join(f"({i}, {i})" for i in range(5000))
    query = f"INSERT INTO summary VALUES {rows}"
    assert len(query) > postgres.CLASSIFY_CACHE_MAX_CHARS
    assert postgres._classify_parts(query) == ((), ((None, "public", "summary"),))
    assert postgres._classify_parts_cached.cache_info().currsize == 0


def test_cached_results_cannot_be_mutated():
    reads, writes = postgres._classify_parts("INSERT INTO summary SELECT id FROM orders")
    assert isinstance(reads, tuple) and isinstance(writes, tuple)
    with pytest.raises(AttributeError):
        reads.append((None, "public", "evil"))  # type: ignore[attr-defined]
    with pytest.raises(TypeError):
        reads[0] = (None, "public", "evil")  # type: ignore[index]
    with pytest.raises(TypeError):
        reads[0][2] = "evil"  # type: ignore[index]
    assert postgres._classify_parts("INSERT INTO summary SELECT id FROM orders") == (
        ((None, "public", "orders"),),
        ((None, "public", "summary"),),
    )


def test_classify_hands_out_fresh_lists():
    reads, _ = postgres._classify("SELECT id FROM orders")
    reads.append("public.evil")
    assert postgres._classify("SELECT id FROM orders") == (["public.orders"], [])
