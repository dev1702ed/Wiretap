"""HTTPEmitter against a tiny http.server running in a thread. No backend needed.

The hard requirement under test: emit() never blocks the caller and never
raises. Delivery problems are the worker's, and every event it cannot deliver
is counted.
"""

import json
import logging
import os
import socket
import threading
import time
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from dcp.config import JobIdentity
from dcp.emitters.http import HTTPEmitter
from dcp.envelope import Dataset, DCPEvent, new_id

JOB = JobIdentity("test_job.py", "test-host", 1)


def make_event():
    return DCPEvent(
        trace_id=new_id(),
        edge_id=new_id(),
        op="read",
        dataset=Dataset(namespace="postgres://localhost:5432", name="dcp.public.orders"),
        job=JOB,
    )


class FakeBackend:
    """Records every POST. Answers with `statuses` in turn, then 200.

    Clear `release` to make the handler hang until it is set again; `received`
    is set as soon as a request body has been read.
    """

    def __init__(self):
        self.requests: list[tuple[str, str, list]] = []  # (path, content type, body)
        self.statuses: list[int] = []
        self.received = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.url = ""

    def events(self) -> list[dict]:
        return [event for _, _, body in self.requests if isinstance(body, list) for event in body]


@pytest.fixture
def backend():
    fake = FakeBackend()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            fake.requests.append((self.path, self.headers["Content-Type"], body))
            fake.received.set()
            fake.release.wait(timeout=10)
            status = fake.statuses.pop(0) if fake.statuses else 200
            payload = json.dumps({"accepted": len(body)}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):  # keep test output quiet
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    fake.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield fake
    fake.release.set()
    server.shutdown()
    server.server_close()


@pytest.fixture
def emitters():
    """Collect emitters so every worker thread is stopped after the test."""
    made: list[HTTPEmitter] = []

    def make(endpoint, **kwargs):
        emitter = HTTPEmitter(endpoint, **kwargs)
        made.append(emitter)
        return emitter

    yield make
    for emitter in made:
        emitter.close(timeout=2)


def closed_port() -> int:
    """A local port with nothing listening on it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_delivers_json_arrays_to_events_path(backend, emitters):
    emitter = emitters(backend.url)
    sent = [make_event() for _ in range(3)]
    for event in sent:
        emitter.emit(event)
    emitter.flush(timeout=5)

    assert backend.events() == [event.to_dict() for event in sent]
    for path, content_type, body in backend.requests:
        assert path == "/events"
        assert content_type == "application/json"
        assert isinstance(body, list)
    assert emitter.dropped == 0


def test_batches_what_queued_while_a_post_was_in_flight(backend, emitters):
    emitter = emitters(backend.url)
    backend.release.clear()
    emitter.emit(make_event())
    assert backend.received.wait(timeout=5)
    later = [make_event() for _ in range(5)]
    for event in later:
        emitter.emit(event)
    backend.release.set()
    emitter.flush(timeout=5)

    assert [len(body) for _, _, body in backend.requests] == [1, 5]
    assert backend.requests[1][2] == [event.to_dict() for event in later]


def test_emit_returns_immediately_and_counts_drops_when_queue_full(backend, emitters, caplog):
    emitter = emitters(backend.url, queue_size=10)
    backend.release.clear()
    emitter.emit(make_event())
    assert backend.received.wait(timeout=5)  # worker is now stuck in a POST
    for _ in range(10):
        emitter.emit(make_event())  # fills the queue

    durations = []
    with caplog.at_level(logging.WARNING, logger="dcp"):
        for _ in range(25):
            start = time.perf_counter()
            emitter.emit(make_event())
            durations.append(time.perf_counter() - start)

    assert emitter.dropped == 25
    assert max(durations) < 0.05  # put_nowait; a blocking put would wait on the POST
    assert "queue full" in caplog.text

    backend.release.set()
    emitter.flush(timeout=5)
    assert len(backend.events()) == 11
    assert emitter.dropped == 25


def test_emit_never_raises_when_backend_is_down(emitters, caplog):
    emitter = emitters(f"http://127.0.0.1:{closed_port()}", max_retries=2, backoff=0.01, timeout=1)
    with caplog.at_level(logging.WARNING, logger="dcp"):
        for _ in range(3):
            emitter.emit(make_event())
        emitter.flush(timeout=10)
    assert emitter.dropped == 3
    assert "dropped" in caplog.text


def test_retries_with_backoff_then_delivers(backend, emitters):
    backend.statuses = [500, 503]
    emitter = emitters(backend.url, max_retries=3, backoff=0.01)
    event = make_event()
    emitter.emit(event)
    emitter.flush(timeout=5)
    assert len(backend.requests) == 3
    assert backend.requests[-1][2] == [event.to_dict()]
    assert emitter.dropped == 0


def test_gives_up_after_max_retries(backend, emitters):
    backend.statuses = [500] * 10
    emitter = emitters(backend.url, max_retries=2, backoff=0.01)
    emitter.emit(make_event())
    emitter.flush(timeout=5)
    assert len(backend.requests) == 3  # the first try and two retries
    assert emitter.dropped == 1


def test_rejected_batch_is_not_retried(backend, emitters):
    backend.statuses = [422]
    emitter = emitters(backend.url, max_retries=3, backoff=0.01)
    emitter.emit(make_event())
    emitter.flush(timeout=5)
    assert len(backend.requests) == 1
    assert emitter.dropped == 1


@pytest.mark.parametrize("kwargs", [{"queue_size": 0}, {"batch_size": 0}])
def test_queue_is_always_bounded(kwargs):
    """queue.Queue(maxsize=0) would be unbounded."""
    with pytest.raises(ValueError):
        HTTPEmitter("http://127.0.0.1:1", **kwargs)


def test_emit_after_close_is_counted(backend, emitters):
    emitter = emitters(backend.url)
    emitter.close(timeout=2)
    emitter.emit(make_event())
    assert emitter.dropped == 1
    assert backend.requests == []


@pytest.mark.skipif(not hasattr(os, "fork"), reason="os.fork is not available here")
def test_forked_child_delivers_its_own_events_exactly_once(backend):
    """Fork while one event is in flight and one is queued. The parent still
    owns both; the child must send only what it emits itself."""
    emitter = HTTPEmitter(backend.url, max_retries=0)
    backend.release.clear()
    in_flight, queued = make_event(), make_event()
    emitter.emit(in_flight)
    assert backend.received.wait(timeout=5)
    emitter.emit(queued)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)  # forking with threads
        pid = os.fork()
    if pid == 0:  # child: never return into pytest
        code = 1
        try:
            child_event = make_event()
            emitter.emit(child_event)
            emitter.close(timeout=10)
            print(child_event.edge_id, flush=True)
            code = 0 if emitter.dropped == 0 else 2
        finally:
            os._exit(code)

    backend.release.set()
    _, status = os.waitpid(pid, 0)
    emitter.close(timeout=10)
    assert os.waitstatus_to_exitcode(status) == 0

    received = [event["edge_id"] for event in backend.events()]
    child_ids = set(received) - {in_flight.edge_id, queued.edge_id}
    assert received.count(in_flight.edge_id) == 1
    assert received.count(queued.edge_id) == 1
    assert len(child_ids) == 1
    assert len(received) == 3
    assert emitter.dropped == 0
