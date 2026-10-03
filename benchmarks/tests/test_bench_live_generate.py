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
    def __init__(self, value: bytes, error=None):
        self._value, self._error = value, error

    def value(self):
        return self._value

    def error(self):
        return self._error


class FakeKafka:
    """confluent_kafka stand-in. Records produce/subscribe/poll; serves `queue`."""

    def __init__(self, log: list, queue: list):
        log_, queue_ = log, queue

        class Producer:
            def __init__(self, config):
                log_.append(("producer", config["bootstrap.servers"]))

            def produce(self, topic, value=None):
                log_.append(("produce", topic, value.decode()))

            def flush(self, timeout):
                return 0

        class Consumer:
            def __init__(self, config):
                log_.append(
                    ("consumer", config["group.id"], config["auto.offset.reset"])
                )

            def subscribe(self, topics):
                log_.append(("subscribe", tuple(topics)))

            def poll(self, timeout):
                return queue_.pop(0) if queue_ else None

            def close(self):
                log_.append(("close",))

        self.module = types.SimpleNamespace(Producer=Producer, Consumer=Consumer)


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
def fakes(monkeypatch):
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
            calls.append(("subscribe", (step["consume"],)))
    return calls


def records_to_serve(process: dict) -> list[FakeMessage]:
    return [
        FakeMessage(s["record"].encode()) for s in process["steps"] if "consume" in s
    ]


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
    calls = [c for c in log if c[0] in ("sql", "produce", "subscribe")]
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
    assert [
        c for c in log if c[0] in ("sql", "produce", "subscribe")
    ] == expected_calls(process)
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
    """The generated consume() on its own, with a short timeout."""
    log, queue = fakes
    namespace = run_source(generate._PRELUDE)
    namespace["CONSUME_TIMEOUT_S"] = 0.2
    return namespace["consume"], log, queue


def test_consume_accepts_the_expected_record(consume):
    fn, log, queue = consume
    queue.append(FakeMessage(b"from_orders"))
    fn("enriched_orders", "from_orders", "group-1")
    assert ("consumer", "group-1", "earliest") in log
    assert log[-1] == ("close",)


def test_consume_fails_loudly_on_the_wrong_record(consume):
    fn, log, queue = consume
    queue.append(FakeMessage(b"from_refunds"))
    with pytest.raises(
        SystemExit, match="expected record 'from_orders'.*got 'from_refunds'"
    ):
        fn("enriched_orders", "from_orders", "g")
    assert log[-1] == ("close",)


def test_consume_fails_loudly_when_nothing_arrives(consume):
    fn, _log, _queue = consume
    with pytest.raises(SystemExit, match="no record on 'enriched_orders'"):
        fn("enriched_orders", "from_orders", "g")


def test_consume_fails_loudly_on_a_broker_error(consume):
    fn, _log, queue = consume
    queue.append(FakeMessage(b"", error="broker down"))
    with pytest.raises(SystemExit, match="consume error"):
        fn("enriched_orders", "from_orders", "g")


def test_consume_waits_through_empty_polls(consume):
    fn, _log, queue = consume
    queue += [None, None, FakeMessage(b"r1")]
    fn("enriched_orders", "r1", "g")


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
