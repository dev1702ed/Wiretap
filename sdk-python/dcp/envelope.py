"""The provenance envelope. P1.

Normative definition is spec/envelope.schema.json — this module must stay in
lockstep with it. CI validates emitted events against the schema; if you change
one, change the other in the same PR.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

DCP_VERSION = "0.1"


@dataclass(frozen=True)
class Dataset:
    """Identity: namespace + name, identical to OpenLineage's model.

    Postgres: namespace="postgres://host:port", name="db.schema.table"
    Kafka:    namespace="kafka://broker:port",  name="topic"

    Must be deterministic — the same physical dataset reached two ways has to
    resolve to one node or the graph fragments.
    """

    namespace: str
    name: str


@dataclass(frozen=True)
class DCPEvent:
    """One observed transfer.

    trace_id is constant for an entire multi-hop flow; edge_id/parent form the
    DAG within it. See spec/README.md section 1.
    """

    trace_id: str
    edge_id: str
    op: str  # "read" | "write"
    dataset: Dataset
    job: "object"  # JobIdentity
    parent: list[str] = field(default_factory=list)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    columns: list[str] | None = None

    def to_dict(self) -> dict:
        """Serialise to exactly the shape of spec/envelope.schema.json."""
        d = {
            "dcp_version": DCP_VERSION,
            "trace_id": self.trace_id,
            "edge_id": self.edge_id,
            "parent": list(self.parent),
            "op": self.op,
            "dataset": {"namespace": self.dataset.namespace, "name": self.dataset.name},
            "job": {
                "name": self.job.name,
                "host": self.job.host,
                "pid": self.job.pid,
            },
            "ts": self.ts,
        }
        if self.columns is not None:
            d["columns"] = self.columns
        return d


def new_id() -> str:
    """Generate a trace_id or edge_id.

    UUID4 for now (stdlib, works on every supported Python version).
    Decision (spec/README.md #1): upgrade to UUIDv7 later to match
    OpenLineage's run-ID convention — safe to change anytime since the
    ID is opaque to every downstream consumer.
    """
    import uuid
    return str(uuid.uuid4())