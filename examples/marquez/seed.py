"""Creates the example's tables and two orders. Deliberately NOT instrumented.

Run once before nightly_enrich.py, so that setting up the data does not show up
as lineage. Leaves an existing `orders` table as it is. UNVERIFIED IN CI.
"""

import os

import psycopg

PG_DSN = os.environ.get(
    "DCP_PG_DSN", "postgresql://postgres:postgres@localhost:5432/dcp"
)

with psycopg.connect(PG_DSN, autocommit=True) as conn:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS orders (id int PRIMARY KEY, total numeric)"
    )
    if conn.execute("SELECT count(*) FROM orders").fetchone()[0] == 0:
        conn.execute("INSERT INTO orders VALUES (1, 10.5), (2, 20)")
    conn.execute("CREATE TABLE IF NOT EXISTS order_totals (payload text)")
print("orders and order_totals are ready")
