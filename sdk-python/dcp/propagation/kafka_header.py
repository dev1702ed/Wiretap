"""Kafka propagation via record header. P2.

Header key: `dcp-context`. A real metadata channel (KIP-82), so this is the
clean case — no smuggling.
"""

HEADER_KEY = "dcp-context"


def inject(headers: list | None, trace_id: str, parent: str | None) -> list:
    """Add the DCP context header to an outgoing record.

    TODO(P2): preserve existing headers; never overwrite the caller's.
    """
    raise NotImplementedError("P2")


def extract(headers: list | None) -> tuple[str | None, str | None]:
    """Recover (trace_id, parent) from an inbound record's headers."""
    raise NotImplementedError("P2")
