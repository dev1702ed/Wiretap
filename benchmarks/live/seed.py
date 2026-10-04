"""Reset the live benchmark data. Runs WITHOUT DCP, so set-up never appears as lineage. P5.

    python benchmarks/live/seed.py [--topic NAME ...]
    python benchmarks/live/seed.py --key benchmarks/ground_truth/generated/scale_s01.json

Destructive, by design: it DROPS and re-creates every table the answer keys
use, in database `dcp` on localhost:5432, and deletes and re-creates the Kafka
topic `enriched_orders` (plus any --topic) on localhost:9092 with exactly one
partition. Leftover records from an earlier run would otherwise be read first.

With --key (P5.1), it instead drops and re-creates a GENERATED key's own
tables (named gen_*, with the rows the key lists) and topics (gen_*).

The live harness runs this as its own process with DCP stripped from the
environment. The password comes from DCP_PG_PASSWORD (default `dcp`).
"""

import argparse
import os
import sys
import time

# Every table any answer key uses, with matching columns.
TABLES = {
    "orders": "id int, total numeric",
    "refunds": "id int, amount numeric",
    "summary": "id int, total numeric",
    "refund_summary": "id int, amount numeric",
    "daily_revenue": "id int, total numeric",
}
ROWS = {
    "orders": [(1, "10.50"), (2, "20.00"), (3, "7.25"), (4, "99.90")],
    "refunds": [(1, "2.50"), (3, "1.25")],
}
TOPIC = "enriched_orders"
PG_CONNINFO = "host=localhost port=5432 dbname=dcp user=postgres"
KAFKA_BOOTSTRAP = "localhost:9092"


def seed_sql() -> list[str]:
    """The statements, in order: drop everything, create, insert source rows."""
    statements = [f"DROP TABLE IF EXISTS {', '.join(TABLES)}"]
    statements += [
        f"CREATE TABLE {table} ({columns})" for table, columns in TABLES.items()
    ]
    for table, rows in ROWS.items():
        values = ", ".join(f"({row_id}, {amount})" for row_id, amount in rows)
        statements.append(f"INSERT INTO {table} VALUES {values}")
    return statements


def pg_password() -> str:
    return os.environ.get("DCP_PG_PASSWORD", "dcp")


def seed_postgres() -> str:
    """Run seed_sql(); return the server version."""
    import psycopg

    with psycopg.connect(PG_CONNINFO, password=pg_password(), autocommit=True) as conn:
        for statement in seed_sql():
            conn.execute(statement)
        return conn.execute("SHOW server_version").fetchone()[0]


def reset_topic(topic: str, timeout: float = 60.0) -> None:
    """Delete `topic`, wait until it is gone, re-create it with one partition."""
    from confluent_kafka import KafkaError, KafkaException
    from confluent_kafka.admin import AdminClient, NewTopic

    admin = AdminClient({"bootstrap.servers": KAFKA_BOOTSTRAP})
    deadline = time.monotonic() + timeout

    def exists() -> bool:
        return topic in admin.list_topics(timeout=10).topics

    if exists():
        try:
            admin.delete_topics([topic], operation_timeout=30)[topic].result()
        except KafkaException as exc:
            if exc.args[0].code() != KafkaError.UNKNOWN_TOPIC_OR_PART:
                raise
        while exists():
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"topic {topic!r} still exists {timeout:.0f} s after deletion"
                )
            time.sleep(0.5)

    while True:
        try:
            admin.create_topics(
                [NewTopic(topic, num_partitions=1, replication_factor=1)]
            )[topic].result()
            break
        except KafkaException as exc:
            # Deletion can still be finishing on the broker after the topic leaves metadata.
            if exc.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                raise
            if time.monotonic() > deadline:
                raise
            time.sleep(0.5)

    while True:
        metadata = admin.list_topics(topic, timeout=10).topics.get(topic)
        ready = (
            metadata is not None
            and metadata.error is None
            and len(metadata.partitions) == 1
        )
        if ready and all(p.leader >= 0 for p in metadata.partitions.values()):
            return
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"topic {topic!r} has no partition leader after {timeout:.0f} s"
            )
        time.sleep(0.5)


def key_seed_sql(key: dict) -> list[str]:
    """A generated key's statements (P5.1): drop its tables, create, insert rows."""
    tables = key["tables"]
    statements = [f"DROP TABLE IF EXISTS {', '.join(tables)}"]
    statements += [
        f"CREATE TABLE {name} ({t['columns']})" for name, t in tables.items()
    ]
    for name, t in tables.items():
        if t["rows"]:
            values = ", ".join(
                "(" + ", ".join(str(v) for v in row) + ")" for row in t["rows"]
            )
            statements.append(f"INSERT INTO {name} VALUES {values}")
    return statements


def seed_key(path: str, kafka: bool = True) -> str:
    """Seed a generated key's own tables and topics. Returns a summary line."""
    import json

    import psycopg

    with open(path, encoding="utf-8") as f:
        key = json.load(f)
    with psycopg.connect(PG_CONNINFO, password=pg_password(), autocommit=True) as conn:
        for statement in key_seed_sql(key):
            conn.execute(statement)
    if kafka:
        for topic in key["topics"]:
            reset_topic(topic)
    return f"seeded {len(key['tables'])} tables and {len(key['topics'])} topics of {key['workload']}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--topic", action="append", default=[], help="another topic to reset"
    )
    parser.add_argument("--no-kafka", action="store_true", help="seed Postgres only")
    parser.add_argument(
        "--key", help="seed a generated key's own tables and topics (P5.1) instead"
    )
    args = parser.parse_args(argv)
    if args.key:
        print(seed_key(args.key, kafka=not args.no_kafka))
        return 0
    version = seed_postgres()
    print(f"seeded {len(TABLES)} tables; PostgreSQL {version}")
    if not args.no_kafka:
        for topic in [TOPIC, *args.topic]:
            reset_topic(topic)
            print(f"reset topic {topic!r} with 1 partition")
    return 0


if __name__ == "__main__":
    sys.exit(main())
