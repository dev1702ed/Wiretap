"""POSTing to a lineage API, and the CLI, against a local http.server stub."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from dcp_openlineage.__main__ import main
from dcp_openlineage.transport import TransportError, post_events

PG = "postgres://localhost:5432"


class StubLineageAPI:
    """Records each request; answers with `statuses` in turn, then 201."""

    def __init__(self):
        self.requests: list[tuple[str, str, dict]] = []
        self.statuses: list[int] = []
        self.url = ""


@pytest.fixture
def api():
    stub = StubLineageAPI()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            stub.requests.append((self.path, self.headers["Content-Type"], body))
            status = stub.statuses.pop(0) if stub.statuses else 201
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    stub.url = f"http://127.0.0.1:{server.server_address[1]}"
    yield stub
    server.shutdown()
    server.server_close()


def no_sleep(_seconds):
    return None


def test_posts_each_event_as_json_to_the_lineage_path(api):
    events = [{"eventType": "START", "n": 1}, {"eventType": "COMPLETE", "n": 2}]
    assert post_events(api.url, events, sleep=no_sleep) == 2
    assert [(path, ctype) for path, ctype, _ in api.requests] == [
        ("/api/v1/lineage", "application/json")
    ] * 2
    assert [body for _, _, body in api.requests] == events


def test_5xx_is_retried_then_delivered(api):
    api.statuses = [500, 503]
    slept = []
    post_events(api.url, [{"n": 1}], max_retries=3, backoff=0.5, sleep=slept.append)
    assert len(api.requests) == 3
    assert slept == [0.5, 1.0]


def test_gives_up_after_max_retries(api):
    api.statuses = [500] * 10
    with pytest.raises(TransportError, match="HTTP 500"):
        post_events(api.url, [{"n": 1}], max_retries=2, sleep=no_sleep)
    assert len(api.requests) == 3


def test_4xx_is_not_retried(api):
    api.statuses = [400]
    with pytest.raises(TransportError, match="HTTP 400"):
        post_events(api.url, [{"n": 1}, {"n": 2}], sleep=no_sleep)
    assert len(api.requests) == 1  # and the second event was never sent


def write_events(path, ev):
    events = [
        ev("r", "read", (PG, "dcp.public.orders")),
        ev("w", "write", (PG, "dcp.public.s"), parent=["r"]),
    ]
    path.write_text("".join(json.dumps(e) + "\n" for e in events))
    return events


def test_cli_posts_translated_events(api, tmp_path, ev, validate):
    events_file = tmp_path / "dcp_events.jsonl"
    write_events(events_file, ev)
    assert main(["--events", str(events_file), "--post", api.url]) == 0
    sent = [body for _, _, body in api.requests]
    validate(sent)
    assert [e["eventType"] for e in sent] == ["START", "COMPLETE"]


def test_cli_fails_with_a_non_zero_exit_on_4xx(api, tmp_path, ev, capsys):
    events_file = tmp_path / "dcp_events.jsonl"
    write_events(events_file, ev)
    api.statuses = [422]
    assert main(["--events", str(events_file), "--post", api.url]) != 0
    assert "HTTP 422" in capsys.readouterr().err


def test_cli_writes_jsonl(tmp_path, ev, validate):
    events_file, out = tmp_path / "dcp_events.jsonl", tmp_path / "ol.jsonl"
    write_events(events_file, ev)
    assert main(["--events", str(events_file), "--out", str(out)]) == 0
    validate([json.loads(line) for line in out.read_text().splitlines()])


def test_cli_rejects_a_bad_line(tmp_path, capsys):
    events_file = tmp_path / "dcp_events.jsonl"
    events_file.write_text("{not json\n")
    assert main(["--events", str(events_file), "--out", str(tmp_path / "o.jsonl")]) == 1
    assert "dcp_events.jsonl:1" in capsys.readouterr().err


def test_cli_needs_an_input(tmp_path):
    with pytest.raises(SystemExit) as exc_info:
        main(["--out", str(tmp_path / "o.jsonl")])
    assert exc_info.value.code != 0


def test_cli_reads_the_backend_event_log(tmp_path, ev):
    store_module = pytest.importorskip("app.store")
    db = tmp_path / "events.db"
    store = store_module.EventStore(db)
    store.append_many(write_events(tmp_path / "unused.jsonl", ev))
    store.close()
    out = tmp_path / "ol.jsonl"
    assert main(["--db", str(db), "--out", str(out)]) == 0
    assert len(out.read_text().splitlines()) == 2


def test_cli_refuses_a_missing_event_log(tmp_path, capsys):
    pytest.importorskip("app.store")
    missing = tmp_path / "nope.db"
    assert main(["--db", str(missing), "--out", str(tmp_path / "o.jsonl")]) == 1
    assert not missing.exists()
