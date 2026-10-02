"""Postgres DBAPI interceptor. P1.

Wraps psycopg's cursor.execute to observe every query. The dataset is derived
from the connection parameters (namespace) plus the tables named in the query
(name).

Known limitation, state it plainly: identifying the table requires reading the
query text. We parse with sqlglot — enough for table-level identity, not enough
for column-to-column mapping, which is explicitly out of v1 scope.
"""

import logging

import sqlglot
from sqlglot import exp

from dcp.config import current_emitter, current_job, sql_propagation_enabled
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
    reads, writes = _classify(sql)
    if not reads and not writes:
        return

    namespace = _namespace(cursor)
    # Dedupe again: `orders` and `dcp.public.orders` are one table once qualified.
    reads = _dedupe([_with_database(cursor, table) for table in reads])
    writes = _dedupe([_with_database(cursor, table) for table in writes])
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
    """Return (tables_read, tables_written).

    INSERT ... SELECT yields both, per the decision to emit two events: it is
    what actually happened on the wire, and the read->write edge then falls out
    of the graph naturally.
    """
    try:
        statement = sqlglot.parse_one(query, dialect="postgres")
    except Exception:  # noqa: BLE001 — unparseable SQL is expected, not fatal
        _log.debug("dcp could not parse query", exc_info=True)
        return [], []
    if statement is None:
        return [], []

    # Only statements that actually move data produce edges. A plain
    # CREATE/DROP/ALTER moves nothing; CTAS (CREATE ... AS SELECT) does.
    if isinstance(statement, exp.Create):
        if statement.expression is None:
            return [], []
    elif not isinstance(statement, (exp.Select, exp.Union, exp.Insert, exp.Update, exp.Delete)):
        return [], []

    writes: list[str] = []
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

    reads = [
        _qualify(table) for table in statement.find_all(exp.Table) if id(table) not in write_nodes
    ]

    return _dedupe(reads), _dedupe(writes)


def _qualify(table: exp.Table) -> str:
    """Table identity as db.schema.table, defaulting the schema to public."""
    parts = [p for p in (table.catalog, table.db, table.name) if p]
    if len(parts) == 1:
        return f"public.{parts[0]}"
    return ".".join(parts)


def _dedupe(names: list[str]) -> list[str]:
    seen, out = set(), []
    for name in names:
        if name not in seen:
            seen.add(name)
            out.append(name)
    return out


def _with_database(cursor, table: str) -> str:
    """db.schema.table, as the spec names Postgres datasets.

    _classify only sees query text, which rarely names the database, so the
    name comes from the live connection. A query that named the catalog
    already has three parts and is left as is.
    """
    if table.count(".") >= 2:
        return table
    return f"{cursor.connection.info.dbname}.{table}"


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
