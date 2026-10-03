"""Postgres DBAPI interceptor. P1.

Wraps psycopg's cursor.execute to observe every query. The dataset is derived
from the connection parameters (namespace) plus the tables named in the query
(name).

Known limitation, state it plainly: identifying the table requires reading the
query text. We parse with sqlglot — enough for table-level identity, not enough
for column-to-column mapping, which is explicitly out of v1 scope.
"""

import functools
import logging

import sqlglot
from sqlglot import exp

from dcp.config import capture_enabled, current_emitter, current_job, sql_propagation_enabled
from dcp.context import ensure_trace, inbound, prior_reads, record_read
from dcp.envelope import Dataset, DCPEvent, new_id
from dcp.propagation import sqlcomment

_log = logging.getLogger("dcp")

_patched = False


def patch_psycopg() -> None:
    """Monkeypatch psycopg so every query is captured."""
    global _patched
    if _patched:
        return

    import psycopg

    original_execute = psycopg.Cursor.execute

    def execute(self, query, params=None, **kwargs):
        if not capture_enabled():  # the kill switch: call straight through
            return original_execute(self, query, params, **kwargs)
        try:
            sent = _outbound(query)
        except Exception:  # noqa: BLE001 — monitor-only: never break the caller
            _log.debug("dcp comment injection failed", exc_info=True)
            sent = query
        result = original_execute(self, sent, params, **kwargs)
        try:
            _capture(self, query)
        except Exception:  # noqa: BLE001 — monitor-only: never break the caller
            _log.debug("dcp capture failed", exc_info=True)
        return result

    psycopg.Cursor.execute = execute
    _patched = True


def _capture(cursor, query) -> None:
    """Emit one event per dataset touched by this statement."""
    sql = _sql_text(cursor, query)
    read_parts, write_parts = _classify_parts(sql)
    if not read_parts and not write_parts:
        return

    namespace = _namespace(cursor)
    # Dedupe again: `orders` and `dcp.public.orders` are one table once qualified.
    reads = _dedupe([_with_database(cursor, parts) for parts in read_parts])
    writes = _dedupe([_with_database(cursor, parts) for parts in write_parts])
    trace_id = ensure_trace()
    emitter = current_emitter()
    job = current_job()

    upstream = inbound()

    # Reads first. Each is parented only to context from a prior hop, never to
    # a sibling read — two tables in one JOIN do not feed each other.
    read_edge_ids: list[str] = []
    for table in reads:
        edge_id = new_id()
        read_edge_ids.append(edge_id)
        emitter.emit(
            DCPEvent(
                trace_id=trace_id,
                edge_id=edge_id,
                parent=upstream,
                op="read",
                dataset=Dataset(namespace=namespace, name=table),
                job=job,
            )
        )
        record_read(f"{namespace}/{table}", edge_id)

    # Precise when the statement names its sources; job-level when the data
    # came through the application; prior-hop context as the last resort.
    write_parents = read_edge_ids or prior_reads() or upstream
    for table in writes:
        emitter.emit(
            DCPEvent(
                trace_id=trace_id,
                edge_id=new_id(),
                parent=write_parents,
                op="write",
                dataset=Dataset(namespace=namespace, name=table),
                job=job,
            )
        )


def _classify(query: str) -> tuple[list[str], list[str]]:
    """Return (tables_read, tables_written) as `schema.table` strings.

    INSERT ... SELECT yields both, per the decision to emit two events: it is
    what actually happened on the wire, and the read->write edge then falls out
    of the graph naturally.
    """
    reads, writes = _classify_parts(query)
    return [_join(parts) for parts in reads], [_join(parts) for parts in writes]


TableParts = tuple[str | None, str, str]  # (catalog or None, schema, table)
Classified = tuple[tuple[TableParts, ...], tuple[TableParts, ...]]  # (reads, writes)

# The parse cache (P5 Stage 5). Classification is a pure function of the query
# text, and a script sends the same parameterised text over and over, so the
# result is cached, keyed on the exact text. Bounded twice: at most
# CLASSIFY_CACHE_SIZE entries, and texts longer than CLASSIFY_CACHE_MAX_CHARS
# (say, an INSERT with thousands of inlined rows) are parsed every time and
# never held, so the cache stays within a few MiB. Results are tuples of
# tuples, so no caller can change what the next one gets.
CLASSIFY_CACHE_SIZE = 1024
CLASSIFY_CACHE_MAX_CHARS = 16 * 1024


def _classify_parts(query: str) -> Classified:
    """_classify, keeping each table's parts apart, through the parse cache."""
    if len(query) > CLASSIFY_CACHE_MAX_CHARS:
        return _classify_parts_uncached(query)
    return _classify_parts_cached(query)


@functools.lru_cache(maxsize=CLASSIFY_CACHE_SIZE)
def _classify_parts_cached(query: str) -> Classified:
    return _classify_parts_uncached(query)


def _classify_parts_uncached(query: str) -> Classified:
    """_classify, keeping each table's parts apart: (catalog, schema, table).

    Unquoted identifiers are folded to lower case, as Postgres folds them, so
    `FROM Orders` and `FROM orders` name one table. Quoted parts are kept
    exactly. Keeping the parts separate is what lets the database be added by
    structure (was a catalog named?) rather than by counting dots, which a
    quoted name like "a.b" would defeat.
    """
    try:
        statement = sqlglot.parse_one(query, dialect="postgres")
    except Exception:  # noqa: BLE001 — unparseable SQL is expected, not fatal
        _log.debug("dcp could not parse query", exc_info=True)
        return (), ()
    if statement is None:
        return (), ()

    # Only statements that actually move data produce edges. A plain
    # CREATE/DROP/ALTER moves nothing; CTAS (CREATE ... AS SELECT) does.
    if isinstance(statement, exp.Create):
        if statement.expression is None:
            return (), ()
    elif not isinstance(statement, (exp.Select, exp.Union, exp.Insert, exp.Update, exp.Delete)):
        return (), ()

    writes: list[TableParts] = []
    write_nodes = set()

    # exp.Create is here only for CTAS; plain DDL was filtered out above.
    for node_type in (exp.Insert, exp.Update, exp.Delete, exp.Create):
        for node in statement.find_all(node_type):
            target = node.this
            # CREATE TABLE AS wraps its target in a Schema node.
            if isinstance(target, exp.Schema):
                target = target.this
            if isinstance(target, exp.Table):
                writes.append(_qualify(target))
                write_nodes.add(id(target))

    # A CTE is a name inside the statement, not a table: `WITH x AS (...) ...
    # FROM x` reads what x reads, and those tables are found inside x's body.
    # An unqualified reference to a CTE's name is the CTE; `public.x` is still
    # the table, as Postgres resolves it.
    ctes = {_fold(cte.args["alias"].this) for cte in statement.find_all(exp.CTE)}

    reads = [
        _qualify(table)
        for table in statement.find_all(exp.Table)
        if id(table) not in write_nodes and not _is_cte_reference(table, ctes)
    ]

    return tuple(_dedupe(reads)), tuple(_dedupe(writes))


def _is_cte_reference(table: exp.Table, ctes: set[str]) -> bool:
    qualified = table.args.get("db") or table.args.get("catalog")
    return not qualified and _fold(table.this) in ctes


def _qualify(table: exp.Table) -> TableParts:
    """(catalog, schema, table), case-folded, defaulting the schema to public."""
    catalog = _fold(table.args.get("catalog"))
    schema = _fold(table.args.get("db")) or "public"
    return catalog or None, schema, _fold(table.this)


def _fold(identifier) -> str:
    """An identifier as Postgres resolves it: lower case unless quoted."""
    if identifier is None:
        return ""
    if isinstance(identifier, exp.Identifier):
        return identifier.this if identifier.quoted else identifier.this.lower()
    return identifier.name


def _join(parts: TableParts) -> str:
    return ".".join(p for p in parts if p)


def _dedupe(items: list) -> list:
    seen, out = set(), []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _with_database(cursor, parts: TableParts) -> str:
    """db.schema.table, as the spec names Postgres datasets.

    Query text rarely names the database, so it comes from the live
    connection; a query that named the catalog keeps the catalog it named.
    """
    catalog, schema, table = parts
    return f"{catalog or cursor.connection.info.dbname}.{schema}.{table}"


def _namespace(cursor) -> str:
    """postgres://host:port, from the live connection."""
    info = cursor.connection.info
    return f"postgres://{info.host}:{info.port}"


def _sql_text(cursor, query) -> str:
    """Query text from any form psycopg accepts.

    psycopg.sql.Composed (dynamic table names via sql.Identifier) is common in
    ETL scripts. str() on it gives a repr, not SQL, so those queries were being
    silently missed — a recall hole in exactly the dark-zone scripts DCP exists
    to see.
    """
    if isinstance(query, bytes):
        return query.decode()
    if isinstance(query, str):
        return query
    as_string = getattr(query, "as_string", None)
    if as_string is not None:
        return as_string(cursor)
    return str(query)


def _outbound(query):
    """The query actually sent: with a trace comment only when opted in.

    Trace only, never parents. Parents change on every call, so they would make
    each query's text unique and defeat psycopg's prepared-statement cache. And
    their URL-encoding (e.g. %2C) would put a bare % into the text, which
    psycopg treats as a placeholder in parameterised queries.
    """
    if not sql_propagation_enabled() or not isinstance(query, str):
        return query
    return sqlcomment.inject(query, ensure_trace())
