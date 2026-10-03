"""The overhead query tiers. P5. Fixed: do not change after seeing results.

T5 was written once, before any timing was taken, as a realistic analytical
query over the seeded tables: two CTEs and a third building on them, a join, a
window function, and aggregates.

Plain data, imported by the CPU microbenchmark and by the overhead workers
(which contain no DCP code).
"""

from dataclasses import dataclass

PG_CONNINFO = (
    "host=localhost port=5432 dbname=dcp user=postgres"  # password: PGPASSWORD
)
KAFKA_BOOTSTRAP = "localhost:9092"
KAFKA_TOPIC = "overhead_bench"
KAFKA_MESSAGE_BYTES = 1024

T5_ANALYTICAL = """\
WITH order_refunds AS (
    SELECT
        o.id,
        o.total,
        COALESCE(SUM(r.amount), 0) AS refunded
    FROM orders AS o
    LEFT JOIN refunds AS r
        ON r.id = o.id
    GROUP BY o.id, o.total
),
net AS (
    SELECT
        id,
        total,
        refunded,
        total - refunded AS net_total,
        CASE
            WHEN refunded = 0 THEN 'clean'
            WHEN refunded < total / 2 THEN 'partial'
            ELSE 'heavy'
        END AS refund_band
    FROM order_refunds
),
ranked AS (
    SELECT
        id,
        net_total,
        refund_band,
        RANK() OVER (ORDER BY net_total DESC) AS revenue_rank,
        SUM(net_total) OVER (
            ORDER BY net_total DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS running_net
    FROM net
)
SELECT
    refund_band,
    COUNT(*) AS orders_in_band,
    SUM(net_total) AS band_net,
    MIN(revenue_rank) AS best_rank,
    MAX(running_net) AS running_net_at_band_end
FROM ranked
WHERE net_total >= %s
GROUP BY refund_band
ORDER BY band_net DESC
"""


@dataclass(frozen=True)
class Tier:
    name: str
    label: str
    query: str
    returns_rows: bool
    events_per_call: int  # DCP events one call emits: reads + writes

    def params(self, i: int) -> tuple:
        """Deterministic parameters for call i (ids 1-4 exist in orders)."""
        row_id = 1 + i % 4
        if self.name == "T3":
            return (row_id, 10)
        if self.name == "T5":
            return (0,)
        return (row_id,)


TIERS = [
    Tier("T1", "point read", "SELECT id, total FROM orders WHERE id = %s", True, 1),
    Tier(
        "T2",
        "join",
        "SELECT o.id, o.total, r.amount FROM orders AS o JOIN refunds AS r"
        " ON r.id = o.id WHERE o.id = %s",
        True,
        2,
    ),
    Tier("T3", "insert values", "INSERT INTO summary VALUES (%s, %s)", False, 1),
    Tier(
        "T4",
        "insert-select",
        "INSERT INTO summary SELECT id, total FROM orders WHERE id = %s",
        False,
        2,
    ),
    Tier("T5", "analytical", T5_ANALYTICAL, True, 2),
]
