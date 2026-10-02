"""Producer: reads Postgres `orders`, produces each row to Kafka `enriched_orders`.

A scratch_produce.py-style script for the Marquez example. UNVERIFIED IN CI.
DCP records to dcp_events.jsonl; nothing is sent to Marquez until the bridge runs.
"""

import json
import os

import dcp

dcp.init(emit="file://dcp_events.jsonl")
dcp.patch_psycopg()
dcp.patch_kafka()  # must run before `from confluent_kafka import Producer`

import psycopg  # noqa: E402
from confluent_kafka import Producer  # noqa: E402

PG_DSN = os.environ.get(
    "DCP_PG_DSN", "postgresql://postgres:postgres@localhost:5432/dcp"
)
KAFKA = os.environ.get("DCP_KAFKA", "localhost:9092")

with psycopg.connect(PG_DSN) as conn:
    rows = conn.execute("SELECT * FROM orders").fetchall()

producer = Producer({"bootstrap.servers": KAFKA})
for row in rows:
    producer.produce("enriched_orders", json.dumps([str(value) for value in row]))
producer.flush(10)
print(f"produced {len(rows)} records to enriched_orders")
