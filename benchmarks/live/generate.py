"""Generate plain programs from an answer key's processes. P5.

Every `process` in a ground-truth key becomes a program that does exactly its
steps against real Postgres and Kafka:

- a `script` process becomes a .py file;
- a `notebook` process becomes an .ipynb with a set-up cell, then one step
  per cell.

Consumption is by exact offset (P5.1, B1). A `produce` step logs its record's
(topic, partition, offset), from the delivery callback, as one line of the run
manifest (`manifest.jsonl` in the working directory, which is the workload's
run directory). A `consume` step looks its named record up there, assigns that
partition at that offset, and checks that the message it reads is that record
at that offset. That works for any number of records on a topic, in any order;
P5 read the earliest record, which only worked for small topologies.

The programs contain psycopg and confluent-kafka calls and nothing else: no
DCP import, no lineage code of any kind. DCP sees them only because they run
under dcp-instrument. They are kept with the results, so a reader can check
that for themselves; `dcp_code_in` is the check the harness also runs.

Text only: this module imports neither psycopg nor confluent-kafka, so it can
be tested anywhere.
"""

import json
import re

PG_CONNINFO = (
    "host=localhost port=5432 dbname=dcp user=postgres"  # password: PGPASSWORD
)
KAFKA_BOOTSTRAP = "localhost:9092"
CONSUME_TIMEOUT_S = 30
MANIFEST = "manifest.jsonl"

_DCP_CODE = re.compile(
    r"^\s*(import\s+dcp\b|from\s+dcp\b)|\bdcp\s*\.\s*\w+\s*\(", re.MULTILINE
)


def dcp_code_in(source: str) -> list[str]:
    """Lines of `source` that import or call DCP. Empty for a generated program."""
    return [line for line in source.splitlines() if _DCP_CODE.search(line)]


_PRELUDE = f'''import json
import time

import psycopg
from confluent_kafka import Consumer, Producer, TopicPartition

PG = {PG_CONNINFO!r}  # libpq reads the password from PGPASSWORD
KAFKA = {KAFKA_BOOTSTRAP!r}
CONSUME_TIMEOUT_S = {CONSUME_TIMEOUT_S}
MANIFEST = {MANIFEST!r}  # the run manifest, in the working directory


def sql(cursor, text):
    cursor.execute(text)
    if cursor.description is not None:
        cursor.fetchall()


def produce(record, topic):
    """Produce `record`, and log where it landed in the run manifest."""
    producer = Producer({{"bootstrap.servers": KAFKA}})
    landed = []
    producer.produce(
        topic, value=record.encode(), on_delivery=lambda err, msg: landed.append((err, msg))
    )
    if producer.flush(CONSUME_TIMEOUT_S) != 0 or not landed:
        raise SystemExit(f"record {{record!r}} was not delivered to {{topic!r}}")
    err, msg = landed[0]
    if err is not None:
        raise SystemExit(f"record {{record!r}} failed delivery to {{topic!r}}: {{err}}")
    entry = {{"record": record, "topic": msg.topic(), "partition": msg.partition(),
              "offset": msg.offset()}}
    with open(MANIFEST, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\\n")


def locate(record, topic):
    """(partition, offset) of `record` on `topic`, from the run manifest."""
    try:
        with open(MANIFEST, encoding="utf-8") as f:
            entries = [json.loads(line) for line in f if line.strip()]
    except FileNotFoundError:
        entries = []
    found = [e for e in entries if e["record"] == record and e["topic"] == topic]
    if len(found) != 1:
        raise SystemExit(
            f"the run manifest has {{len(found)}} entries for {{record!r}} on {{topic!r}}"
        )
    return found[0]["partition"], found[0]["offset"]


def consume(topic, record, group):
    """Read exactly `record`: assign its partition at its offset, from the run
    manifest. The record read must be `record`, at that offset, or fail loudly."""
    partition, offset = locate(record, topic)
    consumer = Consumer(
        {{
            "bootstrap.servers": KAFKA,
            "group.id": group,
            "enable.auto.commit": False,
        }}
    )
    consumer.assign([TopicPartition(topic, partition, offset)])
    deadline = time.monotonic() + CONSUME_TIMEOUT_S
    try:
        while time.monotonic() < deadline:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                raise SystemExit(f"consume error on {{topic!r}}: {{msg.error()}}")
            value = msg.value().decode()
            where = (msg.partition(), msg.offset())
            if value != record or where != (partition, offset):
                raise SystemExit(
                    f"expected record {{record!r}} at {{topic!r}} {{(partition, offset)}}, "
                    f"got {{value!r}} at {{where}}"
                )
            return
        raise SystemExit(f"no record on {{topic!r}} within {{CONSUME_TIMEOUT_S}} s")
    finally:
        consumer.close()
'''


def step_code(step: dict) -> str:
    """One answer-key step as one line of plain Python."""
    if "sql" in step:
        return f"sql(cursor, {step['sql']!r})"
    if "produce" in step:
        return f"produce({step['record']!r}, {step['produce']!r})"
    if "consume" in step:
        return f"consume({step['consume']!r}, {step['record']!r}, GROUP)"
    raise ValueError(f"unknown step in answer key: {step}")


def group_id(run_id: str, workload: str, index: int) -> str:
    """A consumer group unique to this run and process: offsets never carry over."""
    return f"live-{run_id}-{workload}-{index}"


def _header(workload: str, job: str) -> str:
    return (
        f'"""Generated by benchmarks/live/generate.py: workload {workload!r}, job {job!r}.\n\n'
        "Plain psycopg and confluent-kafka calls only. This program contains no\n"
        "lineage code; it is captured only because it runs under dcp-instrument.\n"
        '"""\n\n'
    )


def script_source(workload: str, process: dict, group: str) -> str:
    """A plain .py program doing the process's steps, in order."""
    body = "\n".join(f"    {step_code(step)}" for step in process["steps"])
    return (
        _header(workload, process["job"])
        + _PRELUDE
        + f"\n\nGROUP = {group!r}\n\n"
        + "with psycopg.connect(PG, autocommit=True) as conn:\n"
        + "    cursor = conn.cursor()\n"
        + body
        + "\n"
    )


def notebook(workload: str, process: dict, group: str) -> dict:
    """An nbformat v4.5 notebook: a set-up cell, then one cell per step."""
    setup = (
        _header(workload, process["job"])
        + _PRELUDE
        + f"\n\nGROUP = {group!r}\n"
        + "conn = psycopg.connect(PG, autocommit=True)\n"
        + "cursor = conn.cursor()"
    )
    sources = (
        [setup] + [step_code(step) for step in process["steps"]] + ["conn.close()"]
    )
    ids = (
        ["setup"]
        + [f"step-{i}" for i in range(1, len(process["steps"]) + 1)]
        + ["teardown"]
    )
    return {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "id": cell_id,
                "metadata": {},
                "outputs": [],
                "source": source,
            }
            for cell_id, source in zip(ids, sources, strict=True)
        ],
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def notebook_source(nb: dict) -> str:
    """Every cell's source, for the no-DCP-code check."""
    return "\n".join(cell["source"] for cell in nb["cells"])


def write_notebook(nb: dict, path) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(nb, f, indent=1)
        f.write("\n")
