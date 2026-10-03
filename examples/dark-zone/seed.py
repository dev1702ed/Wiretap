"""Create the demo's tables and topic. No DCP code: set-up is not lineage.

Connection details come from the environment (PGHOST, PGUSER, PGPASSWORD,
PGDATABASE: libpq reads them) and KAFKA_BOOTSTRAP.
"""

import os
import time

import psycopg
from confluent_kafka.admin import AdminClient, NewTopic

with psycopg.connect(autocommit=True) as conn:
    conn.execute("DROP TABLE IF EXISTS orders, daily_revenue")
    conn.execute("CREATE TABLE orders (id int, total numeric)")
    conn.execute("CREATE TABLE daily_revenue (id int, total numeric)")
    conn.execute("INSERT INTO orders VALUES (1, 10.50), (2, 20.00), (3, 7.25)")

admin = AdminClient({"bootstrap.servers": os.environ["KAFKA_BOOTSTRAP"]})
if "enriched_orders" not in admin.list_topics(timeout=30).topics:
    admin.create_topics(
        [NewTopic("enriched_orders", num_partitions=1, replication_factor=1)]
    )["enriched_orders"].result()
    while "enriched_orders" not in admin.list_topics(timeout=30).topics:
        time.sleep(0.5)
print("seeded orders and the enriched_orders topic")
