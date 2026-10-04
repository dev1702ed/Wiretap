"""The live harness's generated programs, with fake libraries: no infrastructure.

Every answer key's processes become plain programs with no DCP code that do
exactly the key's steps, in order. The consume step verifies the record it
reads, so topic_fan_in's "the consumer reads producer A's record" is checked
by the run itself.
"""

import json
import re
import sys
import types

import pytest
from harness import kind, load, workloads
from live import generate

KEYS = [load(name) for name in workloads()]
PROCESSES = [(key["workload"], process) for key in KEYS for process in key["processes"]]
IDS = [f"{workload}/{process['job']}" for workload, process in PROCESSES]


class FakeMessage:
    def __init__(self, value: bytes, error=None, topic="t", partition=0, offset=0):
        self._value, self._error = value, error
        self._topic, self._partition, self._offset = topic, partition, offset

    def value(self):
        return self._value

    def error(self):
        return self._error

    def topic(self):
        return self._topic

    def partition(self):
        return self._partition

    def offset(self):
        return self._offset


class FakeKafka:
    """confluent_kafka stand-in. Records produce/assign/poll; serves `queue`.
    Each produced record lands at the next offset of partition 0 of its topic,
    reported through the on_delivery callback at flush(), as librdkafka does."""

    def __init__(self, log: list, queue: list):
        log_, queue_ = log, queue
        offsets: dict = {}

        class TopicPartition:
            def __init__(self, topic, partition, offset):
                self.topic, self.partition, self.offset = topic, partition, offset

        class Producer:
            def __init__(self, config):
                log_.append(("producer", config["bootstrap.servers"]))
                self.pending = []

            def produce(self, topic, value=None, on_delivery=None):
                log_.append(("produce", topic, value.decode()))
                offset = offsets.get(topic, 0)
                offsets[topic] = offset + 1
                msg = FakeMessage(value, topic=topic, partition=0, offset=offset)
                self.pending.append((on_delivery, msg))

            def flush(self, timeout):
                for callback, msg in self.pending:
                    callback(None, msg)
                self.pending = []
                return 0

        class Consumer:
            def __init__(self, config):
                log_.append(
                    ("consumer", config["group.id"], config.get("auto.offset.reset"))
                )

            def assign(self, partitions):
                for tp in partitions:
                    log_.append(("assign", tp.topic, tp.partition, tp.offset))

            def poll(self, timeout):
                return queue_.pop(0) if queue_ else None

            def close(self):
                log_.append(("close",))

        self.module = types.SimpleNamespace(
            Producer=Producer, Consumer=Consumer, TopicPartition=TopicPartition
        )


class FakePsycopg:
    def __init__(self, log: list):
        log_ = log

        class Cursor:
            description = None

            def execute(self, text):
                log_.append(("sql", text))

            def fetchall(self):
                return []

        class Conn:
            def cursor(self):
                return Cursor()

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def close(self):
                log_.append(("conn-close",))

        def connect(conninfo, autocommit=False):
            log_.append(("connect", conninfo, autocommit))
            return Conn()

        self.module = types.SimpleNamespace(connect=connect)


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    """Fake libraries, and a working directory for the run manifest."""
    monkeypatch.chdir(tmp_path)
    log: list = []
    queue: list = []
    monkeypatch.setitem(sys.modules, "psycopg", FakePsycopg(log).module)
    monkeypatch.setitem(sys.modules, "confluent_kafka", FakeKafka(log, queue).module)
    return log, queue


def run_source(source: str) -> dict:
    namespace: dict = {"__name__": "__generated__"}
    exec(compile(source, "<generated>", "exec"), namespace)  # noqa: S102 — the program under test
    return namespace


def expected_calls(process: dict) -> list[tuple]:
    calls = []
    for step in process["steps"]:
        if "sql" in step:
            calls.append(("sql", step["sql"]))
        elif "produce" in step:
            calls.append(("produce", step["produce"], step["record"]))
        else:
            calls.append(("assign", step["consume"], 0, OFFSET))
    return calls


OFFSET = 7  # where records_to_serve puts each consumed record


def records_to_serve(process: dict) -> list[FakeMessage]:
    """The consumed records, served at OFFSET, and logged in the run manifest
    (the working directory is the test's) as an earlier process would have."""
    served = []
    with open(generate.MANIFEST, "a", encoding="utf-8") as f:
        for s in process["steps"]:
            if "consume" in s:
                entry = {"record": s["record"], "topic": s["consume"], "partition": 0}
                f.write(json.dumps(dict(entry, offset=OFFSET)) + "\n")
                served.append(
                    FakeMessage(s["record"].encode(), topic=s["consume"], offset=OFFSET)
                )
    return served


@pytest.mark.parametrize(("workload", "process"), PROCESSES, ids=IDS)
def test_programs_contain_no_dcp_code(workload, process):
    group = generate.group_id("run1", workload, 0)
    sources = [generate.script_source(workload, process, group)]
    sources.append(
        generate.notebook_source(generate.notebook(workload, process, group))
    )
    for source in sources:
        assert generate.dcp_code_in(source) == []
        assert not re.search(r"^\s*(import|from)\s+dcp\b", source, re.MULTILINE)


@pytest.mark.parametrize(("workload", "process"), PROCESSES, ids=IDS)
def test_script_does_the_steps_in_order(workload, process, fakes):
    log, queue = fakes
    queue += records_to_serve(process)
    run_source(generate.script_source(workload, process, "g"))
    calls = [c for c in log if c[0] in ("sql", "produce", "assign")]
    assert calls == expected_calls(process)
    assert log[0] == ("connect", generate.PG_CONNINFO, True)
    assert "password" not in generate.PG_CONNINFO  # libpq takes it from PGPASSWORD


@pytest.mark.parametrize(("workload", "process"), PROCESSES, ids=IDS)
def test_notebook_has_one_cell_per_step(workload, process, fakes):
    log, queue = fakes
    queue += records_to_serve(process)
    nb = generate.notebook(workload, process, "g")
    assert (nb["nbformat"], nb["nbformat_minor"]) == (4, 5)
    cells = nb["cells"]
    assert [c["id"] for c in cells] == (
        ["setup"]
        + [f"step-{i}" for i in range(1, len(process["steps"]) + 1)]
        + ["teardown"]
    )
    assert all(re.fullmatch(r"[A-Za-z0-9_-]+", c["id"]) for c in cells)
    assert [c["source"] for c in cells[1:-1]] == [
        generate.step_code(s) for s in process["steps"]
    ]
    assert all(c["cell_type"] == "code" and c["outputs"] == [] for c in cells)
    namespace: dict = {"__name__": "__notebook__"}
    for cell in cells:  # one kernel namespace, cell after cell
        exec(compile(cell["source"], cell["id"], "exec"), namespace)  # noqa: S102
    assert [c for c in log if c[0] in ("sql", "produce", "assign")] == expected_calls(
        process
    )
    assert log[-1] == ("conn-close",)


def test_notebook_is_written_as_json(tmp_path):
    key = load("notebook")
    (process,) = key["processes"]
    assert kind(process) == "notebook"
    path = tmp_path / process["job"]
    generate.write_notebook(generate.notebook("notebook", process, "g"), path)
    assert json.loads(path.read_text(encoding="utf-8")) == generate.notebook(
        "notebook", process, "g"
    )
    assert b"\r\n" not in path.read_bytes()


@pytest.fixture
def consume(fakes):
    """The generated produce() and consume() on their own, with a short timeout."""
    log, queue = fakes
    namespace = run_source(generate._PRELUDE)
    namespace["CONSUME_TIMEOUT_S"] = 0.2
    return namespace, log, queue


def manifest() -> list[dict]:
    with open(generate.MANIFEST, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def test_produce_logs_where_each_record_landed(consume):
    ns, _log, _queue = consume
    ns["produce"]("from_orders", "enriched_orders")
    ns["produce"]("from_refunds", "enriched_orders")
    ns["produce"]("r9", "other")
    assert manifest() == [
        {
            "record": "from_orders",
            "topic": "enriched_orders",
            "partition": 0,
            "offset": 0,
        },
        {
            "record": "from_refunds",
            "topic": "enriched_orders",
            "partition": 0,
            "offset": 1,
        },
        {"record": "r9", "topic": "other", "partition": 0, "offset": 0},
    ]


def test_consume_seeks_to_the_records_exact_offset(consume):
    """B1: not the earliest record: the named one, wherever it landed."""
    ns, log, queue = consume
    ns["produce"]("from_refunds", "enriched_orders")
    ns["produce"]("from_orders", "enriched_orders")  # offset 1, not the earliest
    queue.append(FakeMessage(b"from_orders", topic="enriched_orders", offset=1))
    ns["consume"]("enriched_orders", "from_orders", "group-1")
    assert ("consumer", "group-1", None) in log
    assert ("assign", "enriched_orders", 0, 1) in log
    assert log[-1] == ("close",)


def test_consume_fails_loudly_on_the_wrong_record(consume):
    ns, log, queue = consume
    ns["produce"]("from_orders", "enriched_orders")
    queue.append(FakeMessage(b"from_refunds", topic="enriched_orders", offset=0))
    with pytest.raises(
        SystemExit, match="expected record 'from_orders'.*got 'from_refunds'"
    ):
        ns["consume"]("enriched_orders", "from_orders", "g")
    assert log[-1] == ("close",)


def test_consume_fails_loudly_on_the_wrong_offset(consume):
    ns, _log, queue = consume
    ns["produce"]("from_orders", "enriched_orders")
    queue.append(FakeMessage(b"from_orders", topic="enriched_orders", offset=3))
    with pytest.raises(
        SystemExit,
        match=r"at 'enriched_orders' \(0, 0\), got 'from_orders' at \(0, 3\)",
    ):
        ns["consume"]("enriched_orders", "from_orders", "g")


def test_consume_fails_loudly_when_the_record_was_never_produced(consume):
    ns, _log, _queue = consume
    with pytest.raises(SystemExit, match="0 entries for 'from_orders'"):
        ns["consume"]("enriched_orders", "from_orders", "g")


def test_consume_fails_loudly_when_nothing_arrives(consume):
    ns, _log, _queue = consume
    ns["produce"]("from_orders", "enriched_orders")
    with pytest.raises(SystemExit, match="no record on 'enriched_orders'"):
        ns["consume"]("enriched_orders", "from_orders", "g")


def test_consume_fails_loudly_on_a_broker_error(consume):
    ns, _log, queue = consume
    ns["produce"]("from_orders", "enriched_orders")
    queue.append(FakeMessage(b"", error="broker down"))
    with pytest.raises(SystemExit, match="consume error"):
        ns["consume"]("enriched_orders", "from_orders", "g")


def test_consume_waits_through_empty_polls(consume):
    ns, _log, queue = consume
    ns["produce"]("r1", "enriched_orders")
    queue += [None, None, FakeMessage(b"r1", topic="enriched_orders", offset=0)]
    ns["consume"]("enriched_orders", "r1", "g")


def test_a_failed_delivery_fails_loudly(consume, monkeypatch):
    ns, _log, _queue = consume
    producer_cls = ns["Producer"]

    class Failing(producer_cls):
        def flush(self, timeout):
            for callback, msg in self.pending:
                callback("broker said no", msg)
            return 0

    ns["Producer"] = Failing
    with pytest.raises(SystemExit, match="failed delivery"):
        ns["produce"]("r1", "enriched_orders")


def test_consumer_groups_are_unique_per_run_and_process():
    groups = {
        generate.group_id(run, key["workload"], index)
        for run in ("run-a", "run-b")
        for key in KEYS
        for index, _ in enumerate(key["processes"])
    }
    assert len(groups) == 2 * len(PROCESSES)


@pytest.mark.parametrize(
    ("line", "flagged"),
    [
        ("import dcp", True),
        ("from dcp import init", True),
        ("from dcp.interceptors import postgres", True),
        ("    dcp.init(emit='console')", True),
        ("dcp . patch_psycopg()", True),
        ("PG = 'host=localhost dbname=dcp user=postgres'", False),
        ("# runs under dcp-instrument", False),
        ("import dcpx", False),
    ],
)
def test_the_dcp_code_check(line, flagged):
    assert bool(generate.dcp_code_in(line)) is flagged


def test_unknown_step_is_rejected():
    with pytest.raises(ValueError, match="unknown step"):
        generate.step_code({"copy": "orders"})
