"""Consumer: reads Kafka `enriched_orders`, writes Postgres `order_totals`.

A scratch_consume.py-style script for the Marquez example. UNVERIFIED IN CI.
The dcp-context header on each record links this run to the producer's trace.
"""

import os

import dcp

dcp.init(emit="file://dcp_events.jsonl")
dcp.patch_psycopg()
dcp.patch_kafka()  # must run before `from confluent_kafka import Consumer`

import psycopg  # noqa: E402
from confluent_kafka import Consumer  # noqa: E402

PG_DSN = os.environ.get(
    "DCP_PG_DSN", "postgresql://postgres:postgres@localhost:5432/dcp"
)
KAFKA = os.environ.get("DCP_KAFKA", "localhost:9092")

consumer = Consumer(
    {
        "bootstrap.servers": KAFKA,
        "group.id": "dcp-marquez-example",
        "auto.offset.reset": "earliest",
    }
)
consumer.subscribe(["enriched_orders"])
loaded = idle_polls = 0
with psycopg.connect(PG_DSN, autocommit=True) as conn:
    while idle_polls < 10:  # stop after ten seconds without a record
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            idle_polls += 1
            continue
        idle_polls = 0
        conn.execute("INSERT INTO order_totals VALUES (%s)", (msg.value().decode(),))
        loaded += 1
consumer.close()
print(f"loaded {loaded} records into order_totals")
