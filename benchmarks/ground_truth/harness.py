"""Replay a ground-truth workload through DCP's real capture code.

The one replay implementation: sdk-python/tests/test_ground_truth.py and
score.py both use it, so the test and the published numbers cannot drift apart.

Each process's steps go through the SDK's actual capture functions
(`_capture` for SQL, `_on_produce` / `_on_consume` for Kafka). Only the I/O is
faked: a cursor whose connection reports host, port and database, and Kafka
messages that carry the headers the producer's capture returned. Each process
runs in a fresh contextvars.Context, standing in for a separate OS process:
the only thing that crosses between them is a record header.

This is not a live run. Live replay against Postgres and Kafka is P5.
"""

import contextvars
import json
import pathlib

from dcp import config
from dcp.emitters.base import Emitter
from dcp.interceptors.kafka import _on_consume, _on_produce
from dcp.interceptors.postgres import _capture

GROUND_TRUTH = pathlib.Path(__file__).resolve().parent
KAFKA_NS = "kafka://localhost:9092"


def workloads() -> list[str]:
    return sorted(p.parent.name for p in GROUND_TRUTH.glob("*/expected_graph.json"))


def load(workload: str) -> dict:
    return json.loads((GROUND_TRUTH / workload / "expected_graph.json").read_text())


def datasets(key: dict) -> dict[str, tuple[str, str]]:
    """Alias -> (namespace, name)."""
    return {alias: (d["namespace"], d["name"]) for alias, d in key["datasets"].items()}


class _Info:
    host = "localhost"
    port = 5432
    dbname = "dcp"


class _Conn:
    info = _Info()


class FakeCursor:
    connection = _Conn()


class FakeMsg:
    def __init__(self, topic, headers):
        self._topic, self._headers = topic, headers

    def error(self):
        return None

    def headers(self):
        return self._headers

    def topic(self):
        return self._topic


class _Collect(Emitter):
    def __init__(self):
        self.events: list[dict] = []

    def emit(self, event) -> None:
        self.events.append(event.to_dict())

    def flush(self, timeout: float = 5.0) -> None:
        return None


def replay(key: dict) -> list[dict]:
    """Run every process's steps, in order, and return the events DCP emitted.

    DCP's emitter and job identity are swapped in for the replay and restored
    afterwards, so the caller's configuration is untouched.
    """
    collect = _Collect()
    records: dict = {}

    def run(steps):
        for step in steps:
            if "sql" in step:
                _capture(FakeCursor(), step["sql"])
            elif "produce" in step:
                records[step["record"]] = _on_produce(KAFKA_NS, step["produce"], None)
            elif "consume" in step:
                _on_consume(KAFKA_NS, FakeMsg(step["consume"], records[step["record"]]))
            else:
                raise ValueError(f"unknown step in answer key: {step}")

    saved = config._emitter, config._job
    try:
        config._emitter = collect
        for process in key["processes"]:
            config._job = config.JobIdentity(process["job"], "bench", 1)
            contextvars.Context().run(run, process["steps"])
    finally:
        config._emitter, config._job = saved
    return collect.events
