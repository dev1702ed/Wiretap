"""Replay every ground-truth answer key LIVE. P5.

Real Postgres (localhost:5432, database `dcp`), real Kafka (localhost:9092),
and each `process` of the key as a real, separate OS process:

1. seed.py resets the tables and the `enriched_orders` topic, in its own
   process with DCP stripped from the environment;
2. generate.py writes each process as a plain program with no DCP code; a
   consume step reads its named record by exact offset, from the run manifest
   that produce steps write (P5.1);
3. a `script` runs as `python -m dcp.instrument python <job>`, the
   dcp-instrument entry point, and a `notebook` runs in a Jupyter kernel
   (nbclient) whose environment carries the same PYTHONPATH and DCP_*
   variables. Each process emits to its own `file://<run dir>/<job>.jsonl`;
4. the events are collected, schema-checked, and scored by
   ground_truth/score.py's own row functions, exactly as replay is.

Everything a run produces (programs, executed notebook, events, logs) is kept
under the run directory, so a reader can check the programs contain no DCP
code. Addresses are fixed: the answer keys' namespaces name them.
"""

import importlib.util
import json
import os
import pathlib
import socket
import subprocess
import sys
import uuid

from harness import kind, load, workloads
from live import generate
from score import score_workload

LIVE = pathlib.Path(__file__).resolve().parent
SEED = LIVE / "seed.py"
SCHEMA = LIVE.parents[1] / "spec" / "envelope.schema.json"
ADDRESSES = {"PostgreSQL": ("localhost", 5432), "Kafka": ("localhost", 9092)}
LIBRARIES = (
    "psycopg",
    "confluent_kafka",
    "nbclient",
    "nbformat",
    "ipykernel",
    "jupyter_client",
)
PROCESS_TIMEOUT_S = 180
KERNEL_NAME = "dcp-live-python"


class LiveUnavailable(RuntimeError):
    """The environment cannot run live: a service is unreachable or a library missing."""


class LiveRunError(RuntimeError):
    """A live process failed. Never scored as a pass."""


def unavailable() -> str | None:
    """Why live runs cannot happen here, or None if they can."""
    missing = [name for name in LIBRARIES if importlib.util.find_spec(name) is None]
    if missing:
        return (
            f"missing {', '.join(missing)}: pip install -r benchmarks/requirements.txt"
        )
    for service, (host, port) in ADDRESSES.items():
        try:
            socket.create_connection((host, port), timeout=3).close()
        except OSError as exc:
            return (
                f"{service} is not reachable at {host}:{port} ({exc}). Live runs need "
                "PostgreSQL on localhost:5432 (database dcp, password from DCP_PG_PASSWORD, "
                "default dcp) and Kafka on localhost:9092"
            )
    return None


def clean_env() -> dict[str, str]:
    """This environment without any DCP configuration, plus the Postgres password."""
    from dcp.instrument import AUTOINSTRUMENT_DIR

    env = {k: v for k, v in os.environ.items() if not k.startswith("DCP_")}
    paths = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
    paths = [
        p for p in paths if os.path.realpath(p) != os.path.realpath(AUTOINSTRUMENT_DIR)
    ]
    if paths:
        env["PYTHONPATH"] = os.pathsep.join(paths)
    else:
        env.pop("PYTHONPATH", None)
    env["PGPASSWORD"] = os.environ.get("DCP_PG_PASSWORD", "dcp")
    return env


def seed(extra_topics=(), key_path=None) -> str:
    """Run seed.py without DCP. Returns its output. With `key_path`, seed a
    generated key's own tables and topics instead of the hand-written keys'."""
    command = [sys.executable, str(SEED)]
    for topic in extra_topics:
        command += ["--topic", topic]
    if key_path is not None:
        command += ["--key", str(key_path)]
    env = clean_env()
    env["DCP_PG_PASSWORD"] = env["PGPASSWORD"]
    result = subprocess.run(
        command, env=env, capture_output=True, text=True, timeout=180, check=False
    )
    if result.returncode != 0:
        raise LiveRunError(f"seeding failed:\n{result.stdout}{result.stderr}")
    return result.stdout


def postgres_version() -> str:
    import psycopg

    with psycopg.connect(
        generate.PG_CONNINFO, password=clean_env()["PGPASSWORD"], autocommit=True
    ) as conn:
        return conn.execute("SHOW server_version").fetchone()[0]


def read_events(path: pathlib.Path) -> list[dict]:
    """The JSONL a process emitted, every event checked against the envelope schema."""
    import jsonschema

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    if not path.exists():
        return []
    events = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    for event in events:
        jsonschema.validate(event, schema)
    return events


def _check_no_dcp_code(job: str, source: str) -> None:
    found = generate.dcp_code_in(source)
    if found:
        raise LiveRunError(f"generated program {job} contains DCP code: {found}")


def _run_script(workload, process, group, run_dir, env, instrument=True) -> dict:
    job = process["job"]
    source = generate.script_source(workload, process, group)
    _check_no_dcp_code(job, source)
    path = run_dir / job
    path.write_text(source, encoding="utf-8", newline="\n")
    command = [sys.executable, str(path)]
    if instrument:  # the dcp-instrument entry point, as `python -m`
        command = [sys.executable, "-m", "dcp.instrument", *command]
    result = subprocess.run(
        command,
        cwd=run_dir,
        env=env,
        capture_output=True,
        text=True,
        timeout=PROCESS_TIMEOUT_S,
        check=False,
    )
    (run_dir / f"{job}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise LiveRunError(
            f"{workload}/{job} exited {result.returncode}:\n{result.stderr}"
        )
    return {"program": path.name, "exit_code": result.returncode}


def _run_notebook(workload, process, group, run_dir, env, instrument=True) -> dict:
    import nbformat
    from dcp.instrument import instrumented_env
    from jupyter_client.kernelspec import KernelSpecManager
    from jupyter_client.manager import KernelManager
    from nbclient import NotebookClient
    from nbclient.exceptions import CellExecutionError

    job = process["job"]
    nb_dict = generate.notebook(workload, process, group)
    _check_no_dcp_code(job, generate.notebook_source(nb_dict))
    path = run_dir / job
    generate.write_notebook(nb_dict, path)

    # A kernel spec pinned to this interpreter, so the kernel has DCP installed.
    kernels = run_dir / "kernels"
    (kernels / KERNEL_NAME).mkdir(parents=True, exist_ok=True)
    spec = {
        "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
        "display_name": "Python (DCP live harness)",
        "language": "python",
    }
    (kernels / KERNEL_NAME / "kernel.json").write_text(
        json.dumps(spec), encoding="utf-8"
    )
    manager = KernelManager(
        kernel_name=KERNEL_NAME,
        kernel_spec_manager=KernelSpecManager(kernel_dirs=[str(kernels)]),
    )
    nb = nbformat.read(path, as_version=4)
    client = NotebookClient(
        nb, km=manager, kernel_name=KERNEL_NAME, timeout=PROCESS_TIMEOUT_S
    )
    try:
        # cleanup_kc: nbclient shuts down only kernels whose manager it created;
        # this one is ours, so ask explicitly. No kernel outlives its notebook.
        client.execute(
            env=instrumented_env(env) if instrument else env,
            cwd=str(run_dir),
            cleanup_kc=True,
        )
    except CellExecutionError as exc:
        raise LiveRunError(f"{workload}/{job} failed in a cell:\n{exc}") from exc
    finally:
        if manager.has_kernel:
            manager.shutdown_kernel(now=True)
    executed = run_dir / (pathlib.Path(job).stem + ".executed.ipynb")
    nbformat.write(nb, executed)
    return {"program": path.name, "executed": executed.name, "exit_code": 0}


def run_process(workload, process, group, run_dir, env, instrument=True) -> dict:
    """Write one process as a plain program and run it: a script, or a notebook."""
    runner = _run_notebook if kind(process) == "notebook" else _run_script
    return runner(workload, process, group, run_dir, env, instrument)


def read_manifest(run_dir: pathlib.Path) -> list[dict]:
    """Where each produced record landed: the run manifest the programs write."""
    path = run_dir / generate.MANIFEST
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def run_workload(
    key: dict, run_dir: pathlib.Path, run_id: str, key_path=None
) -> tuple[dict, list[dict]]:
    """Seed, then run each process of `key` live, in order. Returns (record, events).

    A generated key (`key_path` given) is seeded from its own tables and topics.
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest = run_dir / generate.MANIFEST
    if manifest.exists():
        manifest.unlink()  # a stale manifest would point consumers at old offsets
    seed(key_path=key_path)
    workload = key["workload"]
    processes, events = [], []
    for index, process in enumerate(key["processes"]):
        job = process["job"]
        sink = run_dir / f"{job}.jsonl"
        if sink.exists():
            sink.unlink()
        env = clean_env()
        env["DCP_EMIT"] = "file://" + str(sink)
        env["DCP_JOB_NAME"] = job
        group = generate.group_id(run_id, workload, index)
        record = run_process(workload, process, group, run_dir, env)
        process_events = read_events(sink)
        record.update(
            job=job, kind=kind(process), events=len(process_events), sink=sink.name
        )
        processes.append(record)
        events += process_events
    return {
        "workload": workload,
        "processes": processes,
        "manifest": read_manifest(run_dir),
    }, events


def run_all(out_dir: pathlib.Path, names: list[str] | None = None) -> dict:
    """Run every workload live and score it. Raises LiveUnavailable if it can't."""
    reason = unavailable()
    if reason:
        raise LiveUnavailable(reason)
    run_id = uuid.uuid4().hex[:8]
    results = []
    for name in workloads() if names is None else names:
        key = load(name)
        record, events = run_workload(key, out_dir / name, run_id)
        record["score"] = score_workload(key, events)
        results.append(record)
    return {
        "run_id": run_id,
        "postgres_server_version": postgres_version(),
        "workloads": results,
    }
