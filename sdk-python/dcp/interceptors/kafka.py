"""Kafka interceptor. P2.

The important one: Kafka severs synchronous causality, so this is where the
multi-hop claim is actually tested. Record headers (KIP-82) are a first-class
metadata channel — unlike Postgres, nothing is being smuggled here.
"""


def patch_kafka() -> None:
    """Wrap Producer.produce and Consumer.poll.

    TODO(P2):
      - produce: inject `dcp-context` header, emit a write event
      - poll: extract the header, adopt the trace (context.set_trace),
        emit a read event parented to the upstream edge
      - dataset: namespace="kafka://broker:port", name=topic
    """
    raise NotImplementedError("P2")
