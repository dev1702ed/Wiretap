"""Kafka propagation via record header. P2.

Header key: `dcp-context`. A real metadata channel (KIP-82), stored WITH the
record, so context crosses the async gap attached to the data itself. This is
why Kafka is the easy propagation case, not the hard one.

Value: UTF-8 JSON, {"trace": "<uuid>", "parent": ["<uuid>", ...]}. JSON rather
than sqlcommenter's flat key=value because headers are a structured channel and
the parent list is native to it.

"parent" here means the edge ids a consumer of this record should adopt as its
parents — in practice, the producer's write edge.
"""

import json

from dcp.envelope import is_valid_id

HEADER_KEY = "dcp-context"


def inject(headers, trace_id: str, parent: list[str] | None = None) -> list:
    """Return the caller's headers with the DCP context added.

    Accepts what confluent-kafka accepts: None, a list of (key, value) tuples,
    or a dict. Always returns a list of tuples. Every caller header is kept;
    only a pre-existing `dcp-context` is replaced. If trace_id is malformed,
    the caller's headers come back unchanged.
    """
    if headers is None:
        existing = []
    elif isinstance(headers, dict):
        existing = list(headers.items())
    else:
        existing = list(headers)

    if not is_valid_id(trace_id):
        return existing

    parents = [p for p in (parent or []) if is_valid_id(p)]
    value = json.dumps({"trace": trace_id, "parent": parents}).encode("utf-8")
    kept = [(k, v) for k, v in existing if k != HEADER_KEY]
    return [*kept, (HEADER_KEY, value)]


def extract(headers) -> tuple[str | None, list[str]]:
    """Recover (trace_id, parent_edge_ids) from a consumed record's headers."""
    if not headers:
        return None, []
    items = headers.items() if isinstance(headers, dict) else headers
    for key, value in items:
        if key != HEADER_KEY or value is None:
            continue
        try:
            raw = value.decode("utf-8") if isinstance(value, bytes) else value
            data = json.loads(raw)
        except ValueError:  # covers UnicodeDecodeError and JSONDecodeError
            return None, []
        if not isinstance(data, dict):
            return None, []
        trace_id = data.get("trace")
        if not is_valid_id(trace_id):
            trace_id = None
        raw_parents = data.get("parent")
        parents = (
            [p for p in raw_parents if is_valid_id(p)] if isinstance(raw_parents, list) else []
        )
        return trace_id, parents
    return None, []