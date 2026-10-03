"""dcp-instrument: an untouched script is captured. Real subprocesses, fake libraries.

Each test writes a plain script with no DCP code in it, plus fake `psycopg` and
`confluent_kafka` modules, and runs it as `python -m dcp.instrument python
script.py`: the same code path as the dcp-instrument console script.
"""

import importlib.metadata
import json
import os
import subprocess
import sys
import textwrap

import pytest

from dcp import instrument

FAKE_PSYCOPG = """
SENT = []


class _Info:
    host = "localhost"
    port = 5432
    dbname = "dcp"


class _Conn:
    info = _Info()


class Cursor:
    connection = _Conn()

    def execute(self, query, params=None, **kwargs):
        SENT.append(query)
        return self
"""

FAKE_KAFKA = """
class Producer:
    def __init__(self, config):
        self.config = config
        self.sent = []

    def produce(self, topic, value=None, key=None, headers=None, **kwargs):
        self.sent.append((topic, headers))


class Consumer:
    def __init__(self, config):
        self.config = config
"""

# Imports the libraries before anything else, binding Producer by name: the
# import order patch_kafka() alone cannot handle.
UNTOUCHED = """
from confluent_kafka import Producer
import psycopg

cursor = psycopg.Cursor()
cursor.execute("SELECT id, total FROM orders")
producer = Producer({"bootstrap.servers": "localhost:9092"})
producer.produce("enriched_orders", b"x")
print("sent:", psycopg.SENT[0])
print("script finished")
"""


@pytest.fixture
def workdir(tmp_path):
    fakes = tmp_path / "fakes"
    fakes.mkdir()
    (fakes / "psycopg.py").write_text(FAKE_PSYCOPG)
    (fakes / "confluent_kafka.py").write_text(FAKE_KAFKA)
    (tmp_path / "job.py").write_text(UNTOUCHED)
    return tmp_path


def run(workdir, *command, extra_paths=(), **env_vars):
    """Run `python -m dcp.instrument COMMAND...` with a clean DCP environment."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("DCP_")}
    paths = [str(workdir / "fakes"), *map(str, extra_paths)]
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env.update(env_vars)
    return subprocess.run(
        [sys.executable, "-m", "dcp.instrument", *command],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def read_events(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def emit_to(workdir) -> tuple[str, object]:
    path = workdir / "events.jsonl"
    return "file://" + str(path), path


def test_untouched_script_is_captured(workdir):
    sink, path = emit_to(workdir)
    result = run(workdir, sys.executable, "job.py", DCP_EMIT=sink)
    assert result.returncode == 0, result.stderr
    assert "script finished" in result.stdout
    read, write = read_events(path)
    assert (read["op"], read["dataset"]["name"]) == ("read", "dcp.public.orders")
    assert (write["op"], write["dataset"]) == (
        "write",
        {"namespace": "kafka://localhost:9092", "name": "enriched_orders"},
    )
    assert write["parent"] == [read["edge_id"]]
    assert write["trace_id"] == read["trace_id"]
    assert read["job"]["name"] == "job.py"  # default: the script's basename
    assert "/*" not in result.stdout  # no SQL comment unless opted in


def test_script_contains_no_dcp_code(workdir):
    assert "dcp" not in (workdir / "job.py").read_text().lower()


# `python -m dcp.instrument` itself starts with the same PYTHONPATH, so the
# user's sitecustomize also runs in that parent process. It acts only in the
# child script, so these tests see the chained run and nothing else.
THEIRS = """import os, sys
MARK = "theirs"
if os.path.basename(sys.argv[0]) == "job.py":
"""


def test_pre_existing_sitecustomize_still_runs(workdir):
    theirs = workdir / "theirs"
    theirs.mkdir()
    (theirs / "sitecustomize.py").write_text(THEIRS + "    os.environ['THEIRS_RAN'] = 'yes'\n")
    (workdir / "job.py").write_text(
        UNTOUCHED + "import os, sitecustomize\nprint('chained:', os.environ.get('THEIRS_RAN'),"
        " sitecustomize.MARK)\n"
    )
    sink, path = emit_to(workdir)
    result = run(workdir, sys.executable, "job.py", extra_paths=[theirs], DCP_EMIT=sink)
    assert result.returncode == 0, result.stderr
    assert "chained: yes theirs" in result.stdout
    assert len(read_events(path)) == 2  # and DCP still captured


def test_an_error_in_the_chained_sitecustomize_is_reported_as_python_would(workdir):
    theirs = workdir / "theirs"
    theirs.mkdir()
    (theirs / "sitecustomize.py").write_text(THEIRS + "    raise RuntimeError('their bug')\n")
    sink, path = emit_to(workdir)
    result = run(workdir, sys.executable, "job.py", extra_paths=[theirs], DCP_EMIT=sink)
    assert result.returncode == 0
    assert "Error in sitecustomize" in result.stderr and "their bug" in result.stderr
    assert "script finished" in result.stdout
    assert len(read_events(path)) == 2


@pytest.mark.parametrize(
    "bad_sink", ["bogus://nowhere", "file://{missing}/events.jsonl", "http://:0"]
)
def test_broken_configuration_does_not_stop_the_script(workdir, bad_sink):
    sink = bad_sink.format(missing=workdir / "no" / "such" / "dir")
    result = run(workdir, sys.executable, "job.py", DCP_EMIT=sink)
    assert result.returncode == 0
    assert "script finished" in result.stdout
    assert "Traceback" not in result.stderr
    assert "Error in sitecustomize" not in result.stderr


def test_a_missing_library_is_skipped(workdir):
    (workdir / "fakes" / "confluent_kafka.py").unlink()
    (workdir / "job.py").write_text(
        "import psycopg\npsycopg.Cursor().execute('SELECT 1 FROM orders')\nprint('ok')\n"
    )
    sink, path = emit_to(workdir)
    result = run(workdir, sys.executable, "job.py", DCP_EMIT=sink)
    assert result.returncode == 0, result.stderr
    assert [e["dataset"]["name"] for e in read_events(path)] == ["dcp.public.orders"]


@pytest.mark.parametrize(("code", "expected"), [("raise SystemExit(7)", 7), ("1/0", 1)])
def test_exit_code_passes_through(workdir, code, expected):
    (workdir / "fail.py").write_text(code + "\n")
    assert run(workdir, sys.executable, "fail.py").returncode == expected


def test_a_signal_exit_is_reported_as_a_shell_would(monkeypatch):
    class Killed:
        def __init__(self, *args, **kwargs):
            return None

        def wait(self):
            return -15

    monkeypatch.setattr(instrument.subprocess, "Popen", Killed)
    assert instrument.main(["python", "x.py"]) == 143


def test_job_name_from_the_environment(workdir):
    sink, path = emit_to(workdir)
    result = run(workdir, sys.executable, "job.py", DCP_EMIT=sink, DCP_JOB_NAME="nightly")
    assert result.returncode == 0, result.stderr
    assert {e["job"]["name"] for e in read_events(path)} == {"nightly"}


def test_job_name_under_dash_m_is_the_module(workdir):
    (workdir / "fakes" / "loader_mod.py").write_text(UNTOUCHED)
    sink, path = emit_to(workdir)
    result = run(workdir, sys.executable, "-m", "loader_mod", DCP_EMIT=sink)
    assert result.returncode == 0, result.stderr
    assert {e["job"]["name"] for e in read_events(path)} == {"loader_mod"}


def test_propagate_sql_from_the_environment(workdir):
    sink, path = emit_to(workdir)
    result = run(workdir, sys.executable, "job.py", DCP_EMIT=sink, DCP_PROPAGATE_SQL="1")
    assert result.returncode == 0, result.stderr
    (sent,) = [line for line in result.stdout.splitlines() if line.startswith("sent:")]
    assert "dcp_trace" in sent
    assert read_events(path)[0]["trace_id"] in sent


def test_propagate_sql_is_off_for_other_values(workdir):
    result = run(workdir, sys.executable, "job.py", DCP_PROPAGATE_SQL="0")
    assert result.returncode == 0, result.stderr
    assert "dcp_trace" not in result.stdout


def test_default_sink_is_the_console(workdir):
    result = run(workdir, sys.executable, "job.py")
    assert result.returncode == 0, result.stderr
    events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
    assert [e["op"] for e in events] == ["read", "write"]


def test_instrumented_env_puts_dcp_first_once():
    env = instrument.instrumented_env(
        {"PYTHONPATH": os.pathsep.join(["a", instrument.AUTOINSTRUMENT_DIR, "b"])}
    )
    assert env["PYTHONPATH"].split(os.pathsep) == [instrument.AUTOINSTRUMENT_DIR, "a", "b"]
    assert instrument.instrumented_env({})["PYTHONPATH"] == instrument.AUTOINSTRUMENT_DIR


def test_the_hook_directory_holds_only_sitecustomize():
    """Everything in it becomes importable by top-level name in the program."""
    names = {name for name in os.listdir(instrument.AUTOINSTRUMENT_DIR) if name != "__pycache__"}
    assert names == {"sitecustomize.py"}


def test_usage_and_missing_commands(capsys):
    assert instrument.main([]) == 2
    assert instrument.main(["--help"]) == 0
    assert "usage: dcp-instrument" in capsys.readouterr().out
    assert instrument.main(["dcp-no-such-command-anywhere"]) == 127


def test_console_script_is_declared():
    (entry,) = [
        e
        for e in importlib.metadata.entry_points(group="console_scripts")
        if e.name == "dcp-instrument"
    ]
    assert entry.value == "dcp.instrument:main"


def test_the_fakes_really_are_imported_first(workdir):
    """Guard against a false pass: the subclass swap must have happened at start-up."""
    (workdir / "job.py").write_text(
        textwrap.dedent(
            """
            from confluent_kafka import Producer
            print("patched:", Producer.__module__ != "confluent_kafka")
            """
        )
    )
    result = run(workdir, sys.executable, "job.py")
    assert "patched: True" in result.stdout, result.stderr
