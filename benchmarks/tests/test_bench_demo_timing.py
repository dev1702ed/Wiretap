"""The dark-zone demo timing (P5.2, D2 step 7): examples/dark-zone/time_demo.py,
run on the owner's machine by time-demo.ps1. Docker is not needed here: the
Marquez API check runs against a stub server, and the docker commands against
a fake runner. The record is checked for its format."""

import importlib.util
import json
import pathlib
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

DEMO = pathlib.Path(__file__).resolve().parents[2] / "examples" / "dark-zone"
_spec = importlib.util.spec_from_file_location("time_demo", DEMO / "time_demo.py")
time_demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(time_demo)

KAFKA = {"namespace": "kafka://kafka:9092", "name": "enriched_orders"}
ORDERS = {"namespace": "postgres://postgres:5432", "name": "dcp.public.orders"}
REVENUE = {"namespace": "postgres://postgres:5432", "name": "dcp.public.daily_revenue"}


@pytest.fixture
def marquez():
    """A stub of the three Marquez endpoints the check reads."""
    state = {"jobs": {}}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            prefix = "/api/v1/namespaces/dcp%3A%2F%2Fdark-zone-demo/jobs"
            if self.path == prefix:
                body = {"jobs": [{"name": n} for n in state["jobs"]]}
            elif self.path.startswith(prefix + "/"):
                name = self.path[len(prefix) + 1 :]
                if name not in state["jobs"]:
                    self.send_response(404)
                    self.end_headers()
                    return
                body = state["jobs"][name]
            else:
                self.send_response(404)
                self.end_headers()
                return
            data = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{server.server_address[1]}"
    yield state
    server.shutdown()


def linked_jobs():
    return {
        "nightly_enrich.py": {"name": "nightly_enrich.py", "inputs": [ORDERS], "outputs": [KAFKA]},
        "warehouse_loader.py": {"name": "warehouse_loader.py", "inputs": [KAFKA], "outputs": [REVENUE]},
    }  # fmt: skip


def test_the_check_passes_when_both_jobs_are_linked_through_the_topic(marquez):
    marquez["jobs"] = linked_jobs()
    result = time_demo.check_marquez(marquez["url"])
    assert result["linked"] is True
    assert result["jobs"] == ["nightly_enrich.py", "warehouse_loader.py"]
    assert result["producer_outputs"] == [("kafka://kafka:9092", "enriched_orders")]


@pytest.mark.parametrize(
    "change",
    [
        lambda jobs: jobs.pop("warehouse_loader.py"),  # one job only
        lambda jobs: jobs["warehouse_loader.py"].update(
            inputs=[ORDERS]
        ),  # not via the topic
        lambda jobs: jobs["nightly_enrich.py"].update(
            outputs=[]
        ),  # producer wrote nothing
        lambda jobs: jobs["nightly_enrich.py"]["outputs"][0].update(
            namespace="kafka://x:1"
        ),
    ],
)
def test_the_check_fails_unless_the_path_is_there(marquez, change):
    jobs = json.loads(json.dumps(linked_jobs()))
    change(jobs)
    marquez["jobs"] = jobs
    assert time_demo.check_marquez(marquez["url"])["linked"] is False


def test_an_unreachable_marquez_is_not_linked_yet():
    result = time_demo.check_marquez("http://127.0.0.1:9")
    assert result == {
        "jobs": [],
        "producer_outputs": [],
        "consumer_inputs": [],
        "linked": False,
    }


def test_polling_stops_when_linked_or_at_the_timeout():
    ticks = iter(range(100))
    answers = iter([{"linked": False}, {"linked": False}, {"linked": True}])
    waited, last = time_demo.wait_until_linked(
        "x",
        60,
        clock=lambda: next(ticks),
        sleep=lambda s: None,
        check=lambda b: next(answers),
    )
    assert last == {"linked": True} and waited == 3
    ticks = iter(range(0, 1000, 10))
    waited, last = time_demo.wait_until_linked(
        "x",
        25,
        clock=lambda: next(ticks),
        sleep=lambda s: None,
        check=lambda b: {"linked": False},
    )
    assert last == {"linked": False} and waited == 30


def test_a_cold_run_removes_only_the_demos_images_and_a_warm_run_none(monkeypatch):
    calls = []

    def fake_run(command, check=True):
        calls.append(command)
        if command[-2:] == ["config", "--images"]:
            return subprocess.CompletedProcess(
                command, 0, "postgres:16\nmarquezproject/marquez:0.51.1\n", ""
            )
        if command[:3] == ["docker", "image", "rm"]:
            code = 1 if command[3] == "postgres:16" else 0  # in use by dcp-postgres
            return subprocess.CompletedProcess(command, code, "", "")
        if command[:3] == ["docker", "image", "inspect"]:
            return subprocess.CompletedProcess(command, 0, "sha256:abc", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(time_demo, "run", fake_run)
    monkeypatch.setattr(time_demo, "demo_exit_code", lambda: "0")
    monkeypatch.setattr(
        time_demo, "wait_until_linked", lambda base, timeout: (12.0, {"linked": True})
    )
    cold = time_demo.timed_run("cold", "x", 60)
    assert cold["removed_images"] == ["marquezproject/marquez:0.51.1"]
    assert cold["kept_images"] == ["postgres:16"]
    assert cold["demo_exit_code"] == "0" and cold["seconds"] is not None
    commands = [" ".join(c) for c in calls]
    assert commands[0].endswith("down -v --remove-orphans")
    assert any(c.endswith("up -d --build") for c in commands)
    assert not any(
        "prune" in c or "system" in c for c in commands
    )  # nothing else removed
    calls.clear()
    warm = time_demo.timed_run("warm", "x", 60)
    assert warm["removed_images"] == [] and not any(
        c[:3] == ["docker", "image", "rm"] for c in calls
    )


def test_the_record_format():
    env = {"timestamp_utc": "2026-10-05T10:00:00+00:00", "git_commit": "abc", "git_dirty": False,
           "os": "Windows-11", "docker": "28.0.0", "compose": "2.30.0"}  # fmt: skip
    ok = {"jobs": ["nightly_enrich.py", "warehouse_loader.py"],
          "producer_outputs": [("kafka://kafka:9092", "enriched_orders")],
          "consumer_inputs": [("kafka://kafka:9092", "enriched_orders")], "linked": True}  # fmt: skip
    runs = [
        {"kind": "cold", "seconds": 183.25, "demo_exit_code": "0", "check": ok,
         "kept_images": ["postgres:16"]},
        {"kind": "warm", "seconds": None, "demo_exit_code": "1", "check": dict(ok, linked=False),
         "kept_images": []},
    ]  # fmt: skip
    rows = [{"image": "postgres:16", "id": "sha256:0123456789ab"}]
    text = time_demo.render_record(env, rows, runs)
    assert text.startswith("# Dark-zone demo: time to first graph (`demo-local`)\n")
    assert "| Started (UTC) | 2026-10-05T10:00:00+00:00 |" in text
    assert "| `postgres:16` | `sha256:0123456789ab` |" in text
    assert (
        "| cold | the demo's images removed first (still present, in use elsewhere: `postgres:16`) | 183.2 | yes | 0 | yes |"
        in text
    )
    assert (
        "| warm | every image present; containers and volumes removed first | not reached | **no** | 1 | **no** |"
        in text
    )
    assert "`nightly_enrich.py` outputs: `kafka://kafka:9092` `enriched_orders`" in text
    assert text.endswith("\n") and not text.endswith("\n\n")
    assert time_demo.render_record(env, rows, runs) == text  # deterministic


def test_the_powershell_wrapper_runs_the_helper_and_writes_the_record():
    ps1 = (DEMO / "time-demo.ps1").read_text(encoding="utf-8")
    assert (
        '"examples/dark-zone/time_demo.py", "--out", "docs/results/demo-local.md"'
        in ps1
    )
    assert "[switch]$SkipCold" in ps1 and '"--skip-cold"' in ps1
    assert "exit $LASTEXITCODE" in ps1
