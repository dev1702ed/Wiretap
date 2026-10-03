"""Consumes `enriched_orders` and writes `daily_revenue`. No DCP code.

The dcp-context header on each record, put there by DCP in the producer, links
this run to the producer's trace.
"""

import json
import os
import time

import psycopg
from confluent_kafka import Consumer

consumer = Consumer(
    {
        "bootstrap.servers": os.environ["KAFKA_BOOTSTRAP"],
        "group.id": f"dark-zone-demo-{int(time.time())}",
        "auto.offset.reset": "earliest",
    }
)
consumer.subscribe(["enriched_orders"])
loaded = 0
deadline = time.monotonic() + 60
with psycopg.connect(autocommit=True) as conn:
    while time.monotonic() < deadline:
        msg = consumer.poll(1.0)
        if msg is None:
            if loaded:
                break  # the topic is drained
            continue
        if msg.error():
            raise SystemExit(f"consume error: {msg.error()}")
        order = json.loads(msg.value())
        conn.execute(
            "INSERT INTO daily_revenue VALUES (%s, %s)", (order["id"], order["total"])
        )
        loaded += 1
consumer.close()
if not loaded:
    raise SystemExit("no records arrived on enriched_orders")
print(f"loaded {loaded} records into daily_revenue")
