"""FileEmitter: JSONL, one event per line. The benchmarks' event of record."""

import json
import os
import pathlib
import signal
import threading
import time
import warnings

import jsonschema
import pytest

from dcp.config import JobIdentity
from dcp.emitters.file import FileEmitter
from dcp.envelope import Dataset, DCPEvent, new_id

SCHEMA = json.loads(
    (pathlib.Path(__file__).parents[2] / "spec" / "envelope.schema.json").read_text()
)
JOB = JobIdentity("test_job.py", "test-host", 1)


def make_event(op="read", name="dcp.public.orders", parent=()):
    return DCPEvent(
        trace_id=new_id(),
        edge_id=new_id(),
        op=op,
        dataset=Dataset(namespace="postgres://localhost:5432", name=name),
        job=JOB,
        parent=list(parent),
    )


def read_jsonl(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_round_trip(tmp_path):
    path = tmp_path / "events.jsonl"
    emitter = FileEmitter(str(path))
    read = make_event()
    sent = [read, make_event(op="write", name="dcp.public.summary", parent=[read.edge_id])]
    for event in sent:
        emitter.emit(event)
    emitter.flush()
    emitter.close()

    lines = read_jsonl(path)
    assert lines == [event.to_dict() for event in sent]
    for line in lines:
        jsonschema.validate(line, SCHEMA)


def test_every_line_is_on_disk_without_flush(tmp_path):
    """A script that dies mid-run still leaves what it emitted."""
    path = tmp_path / "events.jsonl"
    emitter = FileEmitter(str(path))
    emitter.emit(make_event())
    assert len(read_jsonl(path)) == 1
    emitter.close()


def test_appends_to_an_existing_log(tmp_path):
    path = tmp_path / "events.jsonl"
    for _ in range(2):
        emitter = FileEmitter(str(path))
        emitter.emit(make_event())
        emitter.close()
    assert len(read_jsonl(path)) == 2


def test_concurrent_emits_never_interleave(tmp_path):
    path = tmp_path / "events.jsonl"
    emitter = FileEmitter(str(path))
    per_thread = [[make_event() for _ in range(200)] for _ in range(8)]

    def emit_all(events):
        for event in events:
            emitter.emit(event)

    threads = [threading.Thread(target=emit_all, args=(events,)) for events in per_thread]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    emitter.close()

    lines = read_jsonl(path)  # raises if any line is torn
    assert sorted(line["edge_id"] for line in lines) == sorted(
        event.edge_id for events in per_thread for event in events
    )


def test_emit_after_close_is_counted_not_raised(tmp_path):
    emitter = FileEmitter(str(tmp_path / "events.jsonl"))
    emitter.close()
    emitter.emit(make_event())
    emitter.flush()
    assert emitter.dropped == 1


@pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is not available here")
def test_forked_child_can_emit_even_if_the_lock_was_held(tmp_path):
    """Fork while another holder has the write lock: the child re-creates it."""
    path = tmp_path / "events.jsonl"
    emitter = FileEmitter(str(path))
    child_event = make_event()
    emitter._lock.acquire()  # stands in for another thread mid-write
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        pid = os.fork()
    if pid == 0:
        try:
            emitter.emit(child_event)
        finally:
            os._exit(0)
    emitter._lock.release()

    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        done, _ = os.waitpid(pid, os.WNOHANG)
        if done:
            break
        time.sleep(0.05)
    else:
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        pytest.fail("child deadlocked on the inherited lock")
    emitter.close()
    assert [line["edge_id"] for line in read_jsonl(path)] == [child_event.edge_id]
