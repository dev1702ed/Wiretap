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


@pytest.mark.parametrize("value", ["off", "OFF", "0", "false", "no"])
def test_capture_off_keeps_the_patches_and_captures_nothing(workdir, value):
    """The kill switch: wrappers installed, program unchanged, no events, no comment."""
    (workdir / "job.py").write_text(
        UNTOUCHED + 'print("patched:", Producer.__module__ != "confluent_kafka")\n'
    )
    sink, path = emit_to(workdir)
    result = run(
        workdir, sys.executable, "job.py", DCP_EMIT=sink, DCP_CAPTURE=value, DCP_PROPAGATE_SQL="1"
    )
    assert result.returncode == 0, result.stderr
    assert "script finished" in result.stdout and "patched: True" in result.stdout
    assert "sent: SELECT id, total FROM orders\n" in result.stdout  # no trace comment
    assert not path.exists() or read_events(path) == []


@pytest.mark.parametrize("value", ["", "on", "1", "offline"])
def test_capture_stays_on_for_other_values(workdir, value):
    sink, path = emit_to(workdir)
    result = run(workdir, sys.executable, "job.py", DCP_EMIT=sink, DCP_CAPTURE=value)
    assert result.returncode == 0, result.stderr
    assert [e["op"] for e in read_events(path)] == ["read", "write"]


def test_null_sink_runs_the_program_and_records_nothing(workdir):
    result = run(workdir, sys.executable, "job.py", DCP_EMIT="null://")
    assert result.returncode == 0, result.stderr
    assert "script finished" in result.stdout
    assert not [line for line in result.stdout.splitlines() if line.startswith("{")]


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


# P5.1 (A5): post-import hooks instead of eager imports


def test_a_program_that_never_imports_the_libraries_never_loads_them(workdir):
    """Neither psycopg, confluent_kafka nor sqlglot (DCP's own parser) is loaded."""
    (workdir / "plain.py").write_text(
        "import sys\n"
        "names = ('psycopg', 'confluent_kafka', 'sqlglot', 'concurrent.futures.thread')\n"
        "print('loaded:', sorted(n for n in names if n in sys.modules))\n"
        "print('dcp:', 'dcp' in sys.modules)\n"
    )
    sink, _ = emit_to(workdir)
    result = run(workdir, sys.executable, "plain.py", DCP_EMIT=sink)
    assert result.returncode == 0, result.stderr
    assert "loaded: []" in result.stdout
    assert "dcp: True" in result.stdout  # instrumented all the same


def test_from_confluent_kafka_import_producer_binds_the_patched_class(workdir):
    (workdir / "job.py").write_text(
        "from confluent_kafka import Consumer, Producer\n"
        "import confluent_kafka\n"
        "print('patched:', Producer is confluent_kafka.Producer, Producer.__module__)\n"
        "print('consumer:', Consumer is confluent_kafka.Consumer, Consumer.__module__)\n"
    )
    result = run(workdir, sys.executable, "job.py")
    assert result.returncode == 0, result.stderr
    assert "patched: True dcp.interceptors.kafka" in result.stdout
    assert "consumer: True dcp.interceptors.kafka" in result.stdout


def test_a_library_imported_inside_a_function_is_still_captured(workdir):
    (workdir / "job.py").write_text(
        textwrap.dedent(
            """
            def main():
                import psycopg

                psycopg.Cursor().execute("SELECT id, total FROM orders")
                from confluent_kafka import Producer

                Producer({"bootstrap.servers": "localhost:9092"}).produce("enriched_orders", b"x")

            if __name__ == "__main__":
                main()
            """
        )
    )
    sink, path = emit_to(workdir)
    result = run(workdir, sys.executable, "job.py", DCP_EMIT=sink)
    assert result.returncode == 0, result.stderr
    read, write = read_events(path)
    assert (read["op"], read["dataset"]["name"]) == ("read", "dcp.public.orders")
    assert (write["op"], write["dataset"]["name"], write["parent"]) == (
        "write",
        "enriched_orders",
        [read["edge_id"]],
    )


def test_the_hooked_module_keeps_its_real_loader(workdir):
    (workdir / "job.py").write_text(
        "import psycopg, sys\n"
        "print('loader:', type(psycopg.__loader__).__name__, type(psycopg.__spec__.loader).__name__)\n"
        "print('finders:', [type(f).__name__ for f in sys.meta_path].count('PostImportFinder'))\n"
    )
    result = run(workdir, sys.executable, "job.py")
    assert result.returncode == 0, result.stderr
    assert "loader: SourceFileLoader SourceFileLoader" in result.stdout
    assert "finders: 1" in result.stdout  # still waiting for confluent_kafka


def test_a_patch_that_fails_never_breaks_the_import(workdir):
    (workdir / "fakes" / "psycopg.py").write_text("VALUE = 42\n")  # no Cursor to patch
    (workdir / "job.py").write_text("import psycopg\nprint('value:', psycopg.VALUE)\n")
    result = run(workdir, sys.executable, "job.py")
    assert result.returncode == 0, result.stderr
    assert "value: 42" in result.stdout
    assert "Traceback" not in result.stderr


def test_a_library_already_imported_at_start_up_is_patched_at_once(workdir):
    """A .pth file can import a library before sitecustomize runs: it is
    patched at once instead of hooked."""
    (workdir / "fakes" / "early.pth").write_text("import psycopg\n")
    (workdir / "job.py").write_text(
        "import psycopg\nprint('wrapped:', psycopg.Cursor.execute.__module__)\n"
    )
    hook = os.path.join(instrument.AUTOINSTRUMENT_DIR, "sitecustomize.py")
    script = textwrap.dedent(
        f"""
        import importlib.util, runpy, site, sys
        site.addsitedir({str(workdir / "fakes")!r})  # runs early.pth: psycopg is imported
        assert "psycopg" in sys.modules
        spec = importlib.util.spec_from_file_location("dcp_site", {hook!r})
        spec.loader.exec_module(importlib.util.module_from_spec(spec))  # DCP's start-up
        runpy.run_path("job.py", run_name="__main__")
        """
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("DCP_")}
    env.pop("PYTHONPATH", None)
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "wrapped: dcp.interceptors.postgres" in result.stdout


def test_import_dcp_loads_only_what_is_used():
    """P5.1 (A5): the package's names resolve on first use."""
    code = (
        "import sys, dcp\n"
        "heavy = ('dcp.config', 'dcp.interceptors.postgres', 'dcp.interceptors.kafka', 'sqlglot')\n"
        "print('before:', sorted(m for m in heavy if m in sys.modules))\n"
        "print('names:', all(callable(getattr(dcp, n)) for n in dcp.__all__))\n"
        "print('sqlglot:', 'sqlglot' in sys.modules)\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=True
    ).stdout
    assert "before: []" in out
    assert "names: True" in out
    assert "sqlglot: False" in out  # still not parsed anything
