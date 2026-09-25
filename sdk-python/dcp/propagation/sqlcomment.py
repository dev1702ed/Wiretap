"""Postgres propagation via SQL comment. P2.

sqlcommenter-compatible: the context rides in a trailing comment as sorted,
URL-encoded key-value pairs — `SELECT 1 /*dcp_parent='...',dcp_trace='...'*/`

Postgres has no metadata slot in its wire protocol, so the context travels
inside the application payload as a comment the server ignores. It reaches
the server (pg_stat_activity, logs, pgaudit), not the next process that reads
the table: rows carry no per-record metadata. See spec/README.md §3.

The format is deliberately sqlcommenter's, not DCP's own: DCP's whole
positioning is to ride conventions that already exist rather than invent a
wire format. Its escaping rules are also already battle-tested, which matters
because a comment that breaks a query is the one bug monitor-only cannot
tolerate.

Keys:
    dcp_trace   the trace_id
    dcp_parent  upstream edge_ids, comma-joined. Supported by the format, but
                the Postgres interceptor sends dcp_trace only (spec §3).
"""

import re
from urllib.parse import quote, unquote

TRACE_KEY = "dcp_trace"
PARENT_KEY = "dcp_parent"

# Matches a trailing sqlcommenter block: /*key='value',key2='value2'*/
_COMMENT_RE = re.compile(r"/\*(?P<body>[^*]*?=\s*'[^*]*?)\*/\s*;?\s*$")
_PAIR_RE = re.compile(r"(?P<key>[a-zA-Z0-9_%\-]+)\s*=\s*'(?P<value>[^']*)'")

# IDs are UUIDs. Validating the shape is stronger than escaping ad hoc: it
# makes a comment-terminator injection (`*/`) structurally impossible.
_ID_RE = re.compile(r"^[0-9a-fA-F-]{36}$")


def _encode(value: str) -> str:
    """sqlcommenter values are URL-encoded, then single-quoted."""
    return quote(value, safe="")


def _serialize(fields: dict[str, str]) -> str:
    """Sorted key='value' pairs, per the sqlcommenter convention."""
    return ",".join(f"{_encode(k)}='{_encode(v)}'" for k, v in sorted(fields.items()))


def inject(query: str, trace_id: str, parent: list[str] | None = None) -> str:
    """Append the DCP context comment to a query.

    Returns the query unchanged if trace_id is not a well-formed ID, rather
    than risking a malformed statement. Monitor-only means never breaking the
    caller.
    """
    if not trace_id or not _ID_RE.match(trace_id):
        return query

    parents = [p for p in (parent or []) if _ID_RE.match(p)]

    fields = {TRACE_KEY: trace_id}
    if parents:
        fields[PARENT_KEY] = ",".join(parents)

    stripped = query.rstrip()
    trailing_semicolon = stripped.endswith(";")
    if trailing_semicolon:
        stripped = stripped[:-1].rstrip()

    commented = f"{stripped} /*{_serialize(fields)}*/"
    return f"{commented};" if trailing_semicolon else commented


def extract(query: str) -> tuple[str | None, list[str]]:
    """Recover (trace_id, parent_edge_ids) from a query's DCP comment."""
    match = _COMMENT_RE.search(query or "")
    if not match:
        return None, []

    fields = {
        unquote(pair.group("key")): unquote(pair.group("value"))
        for pair in _PAIR_RE.finditer(match.group("body"))
    }

    trace_id = fields.get(TRACE_KEY)
    if trace_id is not None and not _ID_RE.match(trace_id):
        trace_id = None

    raw_parents = fields.get(PARENT_KEY, "")
    parents = [p for p in raw_parents.split(",") if _ID_RE.match(p)]

    return trace_id, parents