"""Kafka interceptor. P2.

Where the multi-hop claim is tested across a real process boundary. Record
headers (KIP-82) are stored with the record, so the producer's write edge
reaches the consumer attached to the data: an attested cross-process edge,
not an inferred one.

How the patch works, and its one sharp edge. confluent-kafka's Producer and
Consumer are C-extension types, which cannot be patched in place ("cannot set
attribute of immutable type"). Like OpenTelemetry's confluent-kafka
instrumentation, DCP swaps Python subclasses onto the module instead. So
patch_kafka() must run BEFORE the application does
`from confluent_kafka import Producer`: a name bound earlier keeps the
original, uninstrumented class. Zero-code auto-instrumentation (decision 6)
would remove this ordering hazard.

Known gaps, stated plainly:
  - A write is emitted when a record is handed to produce(), not on broker
    acknowledgement. A record that later fails delivery still leaves an edge.
    Attestation here means "the application sent it", not "the broker stored it".
  - SerializingProducer / DeserializingConsumer bind the original C types at
    import time and are not covered.
  - A batch from consume() adopts the trace of its last record.
"""

import logging

from dcp.config import current_emitter, current_job
from dcp.context import ensure_trace, inbound, prior_reads, record_read, set_trace
from dcp.envelope import Dataset, DCPEvent, new_id
from dcp.propagation import kafka_header

_log = logging.getLogger("dcp")

_patched = False

# produce(topic, value, key, partition, callback, on_delivery, timestamp, headers):
# after topic, headers is the 7th positional argument.
_HEADERS_POSITION = 6


def patch_kafka() -> None:
    """Swap confluent_kafka.Producer / Consumer for capturing subclasses."""
    global _patched
    if _patched:
        return

    import confluent_kafka

    base_producer = confluent_kafka.Producer
    base_consumer = confluent_kafka.Consumer

    class Producer(base_producer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._dcp_namespace = _namespace(args, kwargs)

        def produce(self, topic, *args, **kwargs):
            try:
                headers = _on_produce(self._dcp_namespace, topic, kwargs.get("headers"))
                # Only set headers by keyword if the caller didn't pass them
                # positionally — otherwise we'd raise "multiple values".
                if len(args) <= _HEADERS_POSITION:
                    kwargs["headers"] = headers
            except Exception:  # noqa: BLE001 — monitor-only: never break the caller
                _log.debug("dcp produce capture failed", exc_info=True)
            return super().produce(topic, *args, **kwargs)

    class Consumer(base_consumer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._dcp_namespace = _namespace(args, kwargs)

        def poll(self, *args, **kwargs):
            msg = super().poll(*args, **kwargs)
            _safe_on_consume(self._dcp_namespace, msg)
            return msg

        def consume(self, *args, **kwargs):
            msgs = super().consume(*args, **kwargs)
            for msg in msgs or ():
                _safe_on_consume(self._dcp_namespace, msg)
            return msgs

    confluent_kafka.Producer = Producer
    confluent_kafka.Consumer = Consumer
    _patched = True


def _on_produce(namespace: str, topic: str, headers):
    """Emit the write, and hand its edge id downstream in the header."""
    trace_id = ensure_trace()
    edge_id = new_id()
    current_emitter().emit(
        DCPEvent(
            trace_id=trace_id,
            edge_id=edge_id,
            # Job-level: a produce names no sources, so it is fed by what this
            # flow read earlier.
            parent=prior_reads() or inbound(),
            op="write",
            dataset=Dataset(namespace=namespace, name=topic),
            job=current_job(),
        )
    )
    # The consumer adopts THIS write as its parent: that is the cross-process edge.
    return kafka_header.inject(headers, trace_id, [edge_id])


def _safe_on_consume(namespace: str, msg) -> None:
    try:
        _on_consume(namespace, msg)
    except Exception:  # noqa: BLE001 — monitor-only: never break the caller
        _log.debug("dcp consume capture failed", exc_info=True)


def _on_consume(namespace: str, msg) -> None:
    """Emit a read parented to the producer's write, and continue its trace."""
    if msg is None or msg.error():
        return
    trace_id, parents = kafka_header.extract(msg.headers())
    if trace_id is not None:
        set_trace(trace_id)  # continue the upstream flow across the async gap
    trace_id = ensure_trace()
    edge_id = new_id()
    topic = msg.topic()
    current_emitter().emit(
        DCPEvent(
            trace_id=trace_id,
            edge_id=edge_id,
            parent=parents,
            op="read",
            dataset=Dataset(namespace=namespace, name=topic),
            job=current_job(),
        )
    )
    record_read(f"{namespace}/{topic}", edge_id)


def _namespace(args, kwargs) -> str:
    """kafka://broker:port, from bootstrap.servers.

    With several brokers the list is sorted and the first taken, so clients
    listing the same brokers in different orders agree. Clients listing
    different subsets of one cluster still fragment into separate namespaces:
    the reason cluster ID was the alternative in spec decision #3.
    """
    config = args[0] if args and isinstance(args[0], dict) else kwargs
    servers = [s.strip() for s in str(config.get("bootstrap.servers", "")).split(",") if s.strip()]
    return f"kafka://{min(servers)}" if servers else "kafka://unknown"