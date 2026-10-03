"""The parse cache (P5 Stage 5, literal-normalised in P5.1 O1): same results,
bounded, and immutable.

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
    """Every answer key's SQL: the hand-written keys and the generated ones."""
    truth = ROOT / "benchmarks" / "ground_truth"
    paths = sorted(truth.glob("*/expected_graph.json")) + sorted(truth.glob("generated/*.json"))
    queries = []
    for path in paths:
        for process in json.loads(path.read_text(encoding="utf-8"))["processes"]:
            queries += [step["sql"] for step in process["steps"] if "sql" in step]
    return sorted(set(queries))


@pytest.fixture(autouse=True)
def empty_cache():
    postgres.clear_classify_cache()
    yield
    postgres.clear_classify_cache()


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


# P5.1 O1: the literal-normalised key


def test_literal_variants_share_one_parse():
    texts = [f"SELECT id, total FROM orders WHERE id = {i}" for i in range(50)]
    for text in texts:
        assert postgres._classify_parts(text) == postgres._classify_parts_uncached(text)
    assert len(postgres._normalised) == 1
    assert (postgres._normalised.misses, postgres._normalised.hits) == (1, 49)


@pytest.mark.parametrize(
    ("query", "key"),
    [
        ("SELECT id FROM orders WHERE id = 42", "SELECT id FROM orders WHERE id = \x00"),
        (
            "SELECT id FROM t1 WHERE x IN (1, 2.5, -3, 1e10, .5)",
            "SELECT id FROM t1 WHERE x IN (\x00)",
        ),
        ("SELECT 'it''s', E'it\\'s' FROM orders", "SELECT \x00 FROM orders"),
        ("SELECT $$ a 'b' $$, $fn$ $$ c $fn$ FROM orders", "SELECT \x00 FROM orders"),
        ("INSERT INTO summary VALUES (1, 2), (3, 4)", "INSERT INTO summary VALUES (\x00), (\x00)"),
        (
            "SELECT c::int, 1::int FROM t WHERE c = $1",
            "SELECT c::int, \x00::int FROM t WHERE c = $1",
        ),
        ("SELECT id FROM orders WHERE id = %s", "SELECT id FROM orders WHERE id = %s"),
        ("SELECT a FROM t WHERE x=E'a\\'b' OR y='c'", "SELECT a FROM t WHERE x=\x00 OR y=\x00"),
        ("SELECT a FROM t WHERE x=e'\\''", "SELECT a FROM t WHERE x=\x00"),
        ("SELECT /* 'x' */ 1 -- 'y\nFROM orders", "SELECT /* 'x' */ \x00 -- 'y\nFROM orders"),
    ],
)
def test_the_normalised_key(query, key):
    assert postgres._cache_key(query) == key


@pytest.mark.parametrize(
    "query",
    [
        'SELECT "Weird 1", "x\'y" FROM "Ta""b 2"',  # quoted identifiers, digits and quotes inside
        'SELECT "$$1$$" FROM "2024"',
        "SELECT a$b, t1.c2 FROM s3.t4 WHERE c = $1",  # identifiers with digits and $
        "SELECT id FROM orders",
    ],
)
def test_identifiers_survive_normalisation(query):
    assert postgres._cache_key(query) == query


def test_dollar_quotes_survive_as_one_literal():
    """A dollar quote holds quotes, $$ and digits; all of it is one literal."""
    q = "SELECT $tag$ it's $$ 1 $notag$ $tag$ FROM orders WHERE x = 'y'"
    assert postgres._cache_key(q) == "SELECT \x00 FROM orders WHERE x = \x00"


@pytest.mark.parametrize(
    "query",
    [
        "SELECT 'unterminated FROM orders",
        'SELECT "unterminated FROM orders',
        "SELECT $ FROM orders",
        "SELECT /* unterminated FROM orders",
        "SELECT /* a /* nested */ 'b' */ id FROM orders",
    ],
)
def test_text_the_pass_cannot_read_is_its_own_key(query):
    assert postgres._cache_key(query) is None
    assert postgres._classify_parts(query) == postgres._classify_parts_uncached(query)


def test_a_parse_failure_never_decides_for_its_siblings(monkeypatch):
    real = postgres._parse_and_classify
    calls = []

    def flaky(query):
        calls.append(query)
        if query.endswith("= 1"):
            return ((), ()), False  # as if sqlglot could not parse this one
        return real(query)

    monkeypatch.setattr(postgres, "_parse_and_classify", flaky)
    assert postgres._classify_parts("SELECT id FROM orders WHERE id = 1") == ((), ())
    assert postgres._classify_parts("SELECT id FROM orders WHERE id = 2") == (
        ((None, "public", "orders"),),
        (),
    )
    assert len(calls) == 2  # the failure was not stored under the shared key


def test_the_normalised_level_is_bounded():
    for i in range(postgres.CLASSIFY_CACHE_SIZE + 50):
        postgres._classify_parts(f"SELECT id FROM t{i} WHERE id = 1")
    assert len(postgres._normalised) == postgres.CLASSIFY_CACHE_SIZE


# Randomised corpora: literal variations must classify exactly as directly;
# identifier variations must never share a key.

TEMPLATES = [
    "SELECT id, total FROM orders WHERE id = {lit}",
    "SELECT o.id FROM orders AS o JOIN refunds AS r ON r.id = o.id WHERE o.total > {lit}",
    "INSERT INTO summary VALUES ({lit}, {lit})",
    "INSERT INTO summary (id, total) VALUES ({lit}, {lit}), ({lit}, {lit})",
    "INSERT INTO summary SELECT id, total FROM orders WHERE id IN ({lits})",
    "UPDATE summary SET total = {lit} WHERE id = {lit}",
    "DELETE FROM summary WHERE total < {lit} AND id NOT IN ({lits})",
    "WITH x AS (SELECT id FROM orders WHERE total >= {lit}) INSERT INTO summary SELECT id, {lit} FROM x",
    'SELECT "Total 2", {lit} FROM "Orders 2024" WHERE "Total 2" = {lit}',
    "SELECT id FROM sales.orders WHERE note = {lit} OR note = {lit}",
    "CREATE TABLE derived AS SELECT id, {lit} AS tag FROM orders",
    "SELECT count(*) FROM orders WHERE created < DATE {str} + INTERVAL {str}",
    "SELECT id FROM orders WHERE id = {lit}; ",
    "SELECT {lit}",
]


def literal(rng):
    kind = rng.randrange(9)
    if kind == 0:
        return str(rng.randrange(10**6))
    if kind == 1:
        return f"-{rng.randrange(1000)}.{rng.randrange(100)}"
    if kind == 2:
        return f"{rng.randrange(1, 9)}.{rng.randrange(10)}e{rng.randrange(-5, 5)}"
    if kind == 3:
        return "'" + rng.choice(["", "x", "it''s", "a,b", "1; DROP", "--", "/*", "$$"]) + "'"
    if kind == 4:
        return "E'" + rng.choice(["a\\'b", "\\n", "c''d", "x"]) + "'"
    if kind == 5:
        return "$$" + rng.choice(["", "it's", "1, 2", "/* x */"]) + "$$"
    if kind == 6:
        return "$q$" + rng.choice(["$$", "'", "x"]) + "$q$"
    if kind == 7:
        return rng.choice(["TRUE", "NULL", "now()"])
    return f".{rng.randrange(100)}"


def variants(count, seed):
    import random

    rng = random.Random(seed)
    out = []
    for _ in range(count):
        template = rng.choice(TEMPLATES)
        text = template
        while "{lit}" in text:
            text = text.replace("{lit}", literal(rng), 1)
        while "{lits}" in text:
            items = ", ".join(literal(rng) for _ in range(rng.randrange(1, 6)))
            text = text.replace("{lits}", items, 1)
        while "{str}" in text:
            text = text.replace("{str}", "'" + str(rng.randrange(1, 28)) + " day'", 1)
        out.append(text)
    return out


def test_randomised_literal_variations_classify_as_directly():
    texts = variants(3000, seed=20261003)
    for text in texts:
        assert postgres._classify_parts(text) == postgres._classify_parts_uncached(text), text
    assert postgres._normalised.hits > 1000  # the variations really did share keys


def identifier(rng):
    name = rng.choice(["orders", "refunds", "summary", "t1", "t2", "a$b", "x_9"])
    if rng.random() < 0.3:
        return '"' + rng.choice(["Orders", "o 1", "1", "x'y", "$$", 'a""b']) + '"'
    return name


def test_statements_differing_only_in_identifiers_never_share_a_key():
    import random

    rng = random.Random(7)
    shapes = [
        "SELECT {i} FROM {t} WHERE {i} = 1",
        "INSERT INTO {t} SELECT {i} FROM {t} WHERE {i} IN (1, 2)",
        "UPDATE {t} SET {i} = 'x' WHERE {i} = $$y$$",
        "SELECT {i} FROM {t} AS {i} JOIN {t} ON {i}.{i} = {t}.{i}",
    ]
    for _ in range(3000):
        shape = rng.choice(shapes)
        a, b = shape, shape
        while "{i}" in a or "{t}" in a:
            slot = "{i}" if "{i}" in a and (rng.random() < 0.5 or "{t}" not in a) else "{t}"
            a = a.replace(slot, identifier(rng), 1)
            b = b.replace(slot, identifier(rng), 1)
        if a != b:
            assert postgres._cache_key(a) != postgres._cache_key(b), (a, b)
