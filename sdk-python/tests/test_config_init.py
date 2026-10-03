"""init(): sink parsing, and shutdown registered for the sinks that buffer."""

import json
import subprocess
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from dcp import config
from dcp.emitters.console import ConsoleEmitter
from dcp.emitters.file import FileEmitter
from dcp.emitters.http import HTTPEmitter
from dcp.emitters.null import NullEmitter


@pytest.fixture
def registered(monkeypatch):
    """Isolate init()'s globals and capture what it registers with atexit."""
    calls: list = []
    monkeypatch.setattr(config, "_emitter", None)
    monkeypatch.setattr(config, "_job", None)
    monkeypatch.setattr(config, "_propagate_sql", False)
    monkeypatch.setattr(config, "_capture", True)
    monkeypatch.setattr(config, "_shutdown_registered", False)
    monkeypatch.setattr(config, "atexit", types.SimpleNamespace(register=calls.append))
    yield calls
    close = getattr(config._emitter, "close", None)
    if close is not None:
        close()


def test_console(registered):
    config.init("console")
    assert isinstance(config.current_emitter(), ConsoleEmitter)
    assert registered == []


def test_file(registered, tmp_path):
    path = tmp_path / "events.jsonl"
    config.init(f"file://{path}")
    emitter = config.current_emitter()
    assert isinstance(emitter, FileEmitter)
    assert emitter.path == str(path)
    assert not emitter.sync  # asynchronous by default since P5.1
    assert registered == [config.shutdown]


@pytest.mark.parametrize(("suffix", "sync"), [("?sync=1", True), ("?sync=0", False)])
def test_file_sync_option(registered, tmp_path, suffix, sync):
    path = tmp_path / "events.jsonl"
    config.init(f"file://{path}{suffix}")
    emitter = config.current_emitter()
    assert emitter.path == str(path) and emitter.sync is sync


def test_http(registered):
    config.init("http://127.0.0.1:8000")
    emitter = config.current_emitter()
    assert isinstance(emitter, HTTPEmitter)
    assert emitter.url == "http://127.0.0.1:8000/events"
    assert registered == [config.shutdown]


def test_null_is_a_diagnostic_sink_that_records_nothing(registered):
    config.init("null://")
    emitter = config.current_emitter()
    assert isinstance(emitter, NullEmitter)
    assert emitter.emit(object()) is None  # discarded, not even serialised
    assert registered == []  # nothing buffered, nothing to flush at exit


def test_capture_is_on_unless_switched_off(registered):
    config.init("console")
    assert config.capture_enabled()
    config.init("console", capture=False)
    assert not config.capture_enabled()
    config.init("console")
    assert config.capture_enabled()


def test_shutdown_is_registered_once(registered, tmp_path):
    config.init(f"file://{tmp_path / 'a.jsonl'}")
    config.init(f"file://{tmp_path / 'b.jsonl'}")
    assert registered == [config.shutdown]


def test_reinit_closes_the_previous_sink(registered, tmp_path):
    config.init(f"file://{tmp_path / 'a.jsonl'}")
    first = config.current_emitter()
    config.init("console")
    assert first._file.closed


def test_marquez_points_at_the_batch_bridge(registered):
    with pytest.raises(NotImplementedError, match=r"file://.*python -m dcp_openlineage"):
        config.init("marquez://localhost:5000")


@pytest.mark.parametrize(
    "spec",
    [
        "",
        "consol",
        "kafka://localhost:9092",
        "https://localhost:8000",
        "file://",
        "http://",
        "null",
        "null://x",
        "http://localhost:notaport",
    ],
)
def test_anything_else_is_rejected(registered, spec):
    with pytest.raises(ValueError):
        config.init(spec)


def test_bad_spec_changes_nothing(registered):
    config.init("console", job_name="first.py")
    emitter, job = config.current_emitter(), config.current_job()
    with pytest.raises(ValueError):
        config.init("bogus://", job_name="second.py")
    assert config.current_emitter() is emitter
    assert config.current_job() is job


def test_script_that_never_calls_shutdown_still_delivers():
    """End to end, in a real subprocess: init, emit, exit. Nothing else."""
    received: list = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.extend(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    script = f"""
import dcp
from dcp import config
from dcp.envelope import Dataset, DCPEvent, new_id

dcp.init(emit="http://127.0.0.1:{server.server_address[1]}", job_name="dark_zone.py")
config.current_emitter().emit(DCPEvent(
    trace_id=new_id(), edge_id=new_id(), op="read",
    dataset=Dataset("postgres://localhost:5432", "dcp.public.orders"),
    job=config.current_job(),
))
"""
    try:
        subprocess.run([sys.executable, "-c", script], check=True, timeout=60)
    finally:
        server.shutdown()
        server.server_close()
    assert [event["job"]["name"] for event in received] == ["dark_zone.py"]
