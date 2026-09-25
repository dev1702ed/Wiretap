"""Kafka produce -> consume parenting, across a simulated process boundary.

No broker needed: the capture logic is exercised directly with fake messages.
A fresh contextvars.Context stands in for a separate process, since the only
thing that can cross between them is the record header.
"""

import contextvars

from dcp.context import ensure_trace, prior_reads, record_read
from dcp.interceptors.kafka import _namespace, _on_consume, _on_produce
from dcp.propagation.kafka_header import extract

NS = "kafka://localhost:9092"


class FakeMsg:
    def __init__(self, topic, headers, error=None):
        self._topic, self._headers, self._error = topic, headers, error

    def error(self):
        return self._error

    def headers(self):
        return self._headers

    def topic(self):
        return self._topic


def test_produce_is_job_level_and_hands_its_edge_downstream(events):
    record_read("postgres://localhost:5432/public.orders", "b0b294e1-91d7-4c7c-8991-ed56c217beb8")
    headers = _on_produce(NS, "enriched_orders", None)
    (write,) = events
    assert write["op"] == "write"
    assert write["dataset"] == {"namespace": NS, "name": "enriched_orders"}
    assert write["parent"] == ["b0b294e1-91d7-4c7c-8991-ed56c217beb8"]
    assert extract(headers) == (write["trace_id"], [write["edge_id"]])


def test_trace_survives_the_process_boundary(events):
    """The multi-hop claim: consumer's read is parented to the producer's write,
    and both share one trace, with only the header crossing between them."""
    headers = _on_produce(NS, "enriched_orders", None)
    (write,) = events

    def consumer_process():
        _on_consume(NS, FakeMsg("enriched_orders", headers))
        read = events[-1]
        assert read["op"] == "read"
        assert read["parent"] == [write["edge_id"]]
        assert read["trace_id"] == write["trace_id"]
        assert ensure_trace() == write["trace_id"]
        assert read["edge_id"] in prior_reads()

    contextvars.Context().run(consumer_process)


def test_consume_without_header_starts_its_own_flow(events):
    _on_consume(NS, FakeMsg("enriched_orders", None))
    (read,) = events
    assert read["parent"] == []


def test_consume_skips_empty_and_error_messages(events):
    _on_consume(NS, None)
    _on_consume(NS, FakeMsg("enriched_orders", None, error="broker down"))
    assert events == []


def test_namespace_is_order_independent():
    a = _namespace(({"bootstrap.servers": "b2:9092,b1:9092"},), {})
    b = _namespace(({"bootstrap.servers": "b1:9092, b2:9092"},), {})
    assert a == b == "kafka://b1:9092"
