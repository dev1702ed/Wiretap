"""Reads orders from Postgres and produces each row to Kafka `enriched_orders`.

A script nobody instrumented: no framework, no scheduler, and no DCP code.
dcp-instrument captures it from the outside.
"""

import json
import os

import psycopg
from confluent_kafka import Producer

with psycopg.connect() as conn:
    rows = conn.execute("SELECT id, total FROM orders").fetchall()

producer = Producer({"bootstrap.servers": os.environ["KAFKA_BOOTSTRAP"]})
for order_id, total in rows:
    producer.produce(
        "enriched_orders", json.dumps({"id": order_id, "total": str(total)})
    )
producer.flush(30)
print(f"produced {len(rows)} records to enriched_orders")
