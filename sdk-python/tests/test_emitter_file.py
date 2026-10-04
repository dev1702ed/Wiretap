"""FileEmitter: JSONL, one event per line. The benchmarks' event of record.

Synchronous (write before emit() returns) is the default; P5.1 (O3) added an
asynchronous mode, `sync=False` (file://path?sync=0), where a background thread
writes. Every property that holds for both is tested for both.
"""

import json
import os
import pathlib
import signal
import subprocess
import sys
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


MODES = pytest.mark.parametrize("sync", [False, True], ids=["async", "sync"])


@MODES
def test_round_trip(tmp_path, sync):
    path = tmp_path / "events.jsonl"
    emitter = FileEmitter(str(path), sync=sync)
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


def test_sync_puts_every_line_on_disk_before_emit_returns(tmp_path):
    """The default: a script killed outright still leaves what it emitted."""
    path = tmp_path / "events.jsonl"
    emitter = FileEmitter(str(path))
    assert emitter.sync
    emitter.emit(make_event())
    assert len(read_jsonl(path)) == 1
    emitter.close()


def test_async_writes_on_its_own_thread_and_flush_waits_for_it(tmp_path):
    path = tmp_path / "events.jsonl"
    emitter = FileEmitter(str(path), sync=False)
    assert not emitter.sync
    emitter._lock.acquire()  # hold the writer: emit() must still return at once
    try:
        started = time.monotonic()
        for _ in range(50):
            emitter.emit(make_event())
        assert time.monotonic() - started < 1.0
        assert read_jsonl(path) == []
    finally:
        emitter._lock.release()
    emitter.flush()
    assert len(read_jsonl(path)) == 50
    emitter.close()


def test_async_keeps_emit_order(tmp_path):
    path = tmp_path / "events.jsonl"
    emitter = FileEmitter(str(path), sync=False)
    sent = [make_event() for _ in range(2000)]
    for event in sent:
        emitter.emit(event)
    emitter.close()
    assert [line["edge_id"] for line in read_jsonl(path)] == [e.edge_id for e in sent]


def test_async_full_queue_drops_and_counts_never_blocks(tmp_path):
    emitter = FileEmitter(str(tmp_path / "events.jsonl"), sync=False, queue_size=2)
    emitter._lock.acquire()  # the worker takes at most one batch, then waits
    try:
        for _ in range(20):
            emitter.emit(make_event())
    finally:
        emitter._lock.release()
    emitter.close()
    written = len(read_jsonl(tmp_path / "events.jsonl"))
    assert emitter.dropped > 0 and written + emitter.dropped == 20


def test_queue_size_must_be_bounded(tmp_path):
    with pytest.raises(ValueError, match="at least 1"):
        FileEmitter(str(tmp_path / "events.jsonl"), sync=False, queue_size=0)


@pytest.mark.parametrize("ending", ["normally", "by an uncaught exception", "by sys.exit(3)"])
def test_async_delivers_everything_when_the_process_ends(tmp_path, ending):
    """dcp.init() registers shutdown() with atexit, which drains the queue."""
    path = tmp_path / "events.jsonl"
    last = {
        "normally": "pass",
        "by an uncaught exception": "raise RuntimeError('boom')",
        "by sys.exit(3)": "sys.exit(3)",
    }[ending]
    script = f"""
import sys
import dcp
from dcp import config
from dcp.envelope import Dataset, DCPEvent, new_id

dcp.init(emit="file://" + sys.argv[1] + "?sync=0", job_name="ends.py")
for _ in range(500):
    config.current_emitter().emit(DCPEvent(
        trace_id=new_id(), edge_id=new_id(), op="read",
        dataset=Dataset("postgres://localhost:5432", "dcp.public.orders"),
        job=config.current_job(),
    ))
{last}
"""
    subprocess.run([sys.executable, "-c", script, str(path)], timeout=60, check=False)
    assert len(read_jsonl(path)) == 500


@MODES
def test_appends_to_an_existing_log(tmp_path, sync):
    path = tmp_path / "events.jsonl"
    for _ in range(2):
        emitter = FileEmitter(str(path), sync=sync)
        emitter.emit(make_event())
        emitter.close()
    assert len(read_jsonl(path)) == 2


@MODES
def test_concurrent_emits_never_interleave(tmp_path, sync):
    path = tmp_path / "events.jsonl"
    emitter = FileEmitter(str(path), sync=sync)
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


@MODES
def test_emit_after_close_is_counted_not_raised(tmp_path, sync):
    emitter = FileEmitter(str(tmp_path / "events.jsonl"), sync=sync)
    emitter.close()
    emitter.emit(make_event())
    emitter.flush()
    assert emitter.dropped == 1


@MODES
@pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is not available here")
def test_forked_child_can_emit_even_if_the_lock_was_held(tmp_path, sync):
    """Fork while another holder has the write lock: the child re-creates it,
    and (async) re-arms its writer thread with an empty queue."""
    path = tmp_path / "events.jsonl"
    emitter = FileEmitter(str(path), sync=sync)
    child_event = make_event()
    emitter._lock.acquire()  # stands in for another thread mid-write
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        pid = os.fork()
    if pid == 0:
        try:
            emitter.emit(child_event)
            emitter.flush()
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
