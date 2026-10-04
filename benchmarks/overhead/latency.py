"""4b: live per-call overhead against Postgres and Kafka. P5.

Configurations (fixed), in this order every round:

    base             no DCP
    file             dcp-instrument, file:// sink (a temp file)
    http             dcp-instrument, http:// sink to a LIVE backend: create_app
                     under uvicorn, one worker, a fresh temp database per round
    http-down        dcp-instrument, http:// sink to a closed port, so the
                     emitter's worker is failing and retrying the whole time
    file+sqlcomment  dcp-instrument, file:// sink, DCP_PROPAGATE_SQL=1
    wrap-only        dcp-instrument, DCP_CAPTURE=off (added in P5.1): the
                     wrappers are installed and call straight through
    capture-null     dcp-instrument, null:// sink (added in P5.1): capture and
                     event construction on the real psycopg path, no delivery

The two ablations were added in P5.1, after P5's results were seen, to
attribute the per-call cost: wrapper (wrap-only), capture and construction
(capture-null - wrap-only), async enqueue (http-down - capture-null), the
synchronous file write (file - http-down), the SQL comment
(file+sqlcomment - file). A profiling round (one extra round per instrumented
configuration, under cProfile, T1 and L1 only) explains each component; it is
never used for a timing.

Every configuration runs pg_worker.py as a fresh subprocess per round; rounds
alternate configurations in the fixed order to cancel drift. Process start-up
is outside the timed loop and is measured separately. Kafka produce() latency
runs the same way for base, file and http with kafka_worker.py.

Per configuration and tier: p50/p95/p99/p99.9 over every timed call. Against
base, paired by round: added p50 and p99 latency, and throughput change, each
with a 95% bootstrap interval over rounds (stats.py), and a verdict against
the targets (< 1 ms p99 added, < 2% throughput loss).

Events delivered are counted, never assumed: lines in the file sink, the
backend's event count for http. For http-down nothing can arrive, so the
backpressure check (backpressure_worker.py, DCP-aware on purpose) reports the
emitter's exact drop count with a deliberately tiny queue.
"""

import json
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request
from dataclasses import asdict, dataclass

from live import run_live
from overhead import stats
from overhead.queries import KAFKA_TOPIC, TIERS

OVERHEAD = pathlib.Path(__file__).resolve().parent
PG_WORKER = OVERHEAD / "pg_worker.py"
KAFKA_WORKER = OVERHEAD / "kafka_worker.py"
BACKPRESSURE_WORKER = OVERHEAD / "backpressure_worker.py"

CONFIGS = (
    "base",
    "file",
    "http",
    "http-down",
    "file+sqlcomment",
    "wrap-only",
    "capture-null",
)
KAFKA_CONFIGS = ("base", "file", "http", "wrap-only", "capture-null")
ADDED_IN_P51 = ("wrap-only", "capture-null")
NO_DELIVERY = {
    "http-down": "not measurable (nothing listens)",
    "wrap-only": "none by design (capture off)",
    "capture-null": "none by design (null:// discards)",
}
PROFILE_TIERS = ("T1", "L1")
# A3's attribution (P5.1): each component is the difference between two
# configurations' per-round values, paired by round, so base cancels out.
COMPONENTS = (
    ("wrapper", "wrap-only", "base"),
    ("capture + construction", "capture-null", "wrap-only"),
    ("async enqueue", "http-down", "capture-null"),
    ("synchronous file write", "file", "http-down"),
    ("SQL comment", "file+sqlcomment", "file"),
)
# Kafka runs no http-down or file+sqlcomment: enqueue is measured against the
# live backend, and the file write against capture-null.
KAFKA_COMPONENTS = (
    ("wrapper", "wrap-only", "base"),
    ("capture + construction", "capture-null", "wrap-only"),
    ("enqueue (http, live backend)", "http", "capture-null"),
    ("synchronous file write", "file", "capture-null"),
)
LATENCY_TARGET_US = 1000.0  # < 1 ms p99 added
THROUGHPUT_TARGET_PCT = 2.0  # < 2% throughput loss
BACKPRESSURE_QUEUE = 8
BACKPRESSURE_BACKOFF_MS = (
    50.0  # the worker's retry backoff; a blocked emit() would show it
)
WORKER_TIMEOUT_S = 1800


@dataclass(frozen=True)
class Mode:
    name: str
    rounds: int
    calls: int
    warmup: int
    kafka_messages: int
    kafka_warmup: int
    startup_reps: int


FULL = Mode(
    "full",
    rounds=10,
    calls=2000,
    warmup=200,
    kafka_messages=10_000,
    kafka_warmup=200,
    startup_reps=20,
)
QUICK = Mode(
    "quick",
    rounds=5,
    calls=300,
    warmup=50,
    kafka_messages=2_000,
    kafka_warmup=50,
    startup_reps=10,
)


def unavailable() -> str | None:
    reason = run_live.unavailable()
    if reason:
        return reason
    import importlib.util

    if importlib.util.find_spec("uvicorn") is None:
        return "missing uvicorn: pip install -r benchmarks/requirements.txt"
    return None


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def reserve_closed_port() -> socket.socket:
    """A port bound but never listening: connections are refused, and no backend
    started later can be given it. Close the socket when done."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    return s


class Backend:
    """The DCP backend (create_app) under uvicorn, one worker, a temp database."""

    def __init__(self, workdir: pathlib.Path):
        self.port = free_port()
        self.url = f"http://127.0.0.1:{self.port}"
        workdir.mkdir(parents=True, exist_ok=True)
        env = run_live.clean_env()
        env["DCP_DB_PATH"] = str(workdir / "events.db")
        self.log = open(workdir / "backend.log", "w", encoding="utf-8")  # noqa: SIM115
        command = [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(self.port),
            "--workers",
            "1",
            "--log-level",
            "warning",
        ]
        self.proc = subprocess.Popen(
            command, env=env, stdout=self.log, stderr=subprocess.STDOUT
        )
        deadline = time.monotonic() + 60
        while True:
            try:
                with urllib.request.urlopen(self.url + "/health", timeout=2):
                    return
            except OSError:
                if self.proc.poll() is not None or time.monotonic() > deadline:
                    self.close()
                    raise RuntimeError(
                        f"backend did not start; see {self.log.name}"
                    ) from None
                time.sleep(0.2)

    def event_count(self) -> int:
        with urllib.request.urlopen(self.url + "/graph", timeout=60) as response:
            return json.loads(response.read())["event_count"]

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.log.close()


def config_env(
    config: str, sink: pathlib.Path, backend_url: str, closed_url: str
) -> dict:
    """The environment for one configuration. base gets no DCP at all."""
    env = run_live.clean_env()
    if config == "base":
        return env
    env["DCP_EMIT"] = {
        "file": "file://" + str(sink),
        "file+sqlcomment": "file://" + str(sink),
        "http": backend_url,
        "http-down": closed_url,
        "wrap-only": "null://",
        "capture-null": "null://",
    }[config]
    if config == "file+sqlcomment":
        env["DCP_PROPAGATE_SQL"] = "1"
    if config == "wrap-only":
        env["DCP_CAPTURE"] = "off"
    return env


def command(config: str, worker: pathlib.Path, *args) -> list[str]:
    plain = [sys.executable, str(worker), *map(str, args)]
    if config == "base":
        return plain
    return [sys.executable, "-m", "dcp.instrument", *plain]


def _run_worker(cmd, env, cwd) -> None:
    result = subprocess.run(
        cmd,
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=WORKER_TIMEOUT_S,
        check=False,
    )
    if result.returncode != 0:
        worker = next(pathlib.Path(c).name for c in cmd if c.endswith("_worker.py"))
        raise RuntimeError(
            f"{worker} failed ({result.returncode}):\n{result.stderr[-3000:]}"
        )


def _count_lines(path: pathlib.Path) -> int:
    if not path.exists():
        return 0
    with open(path, "rb") as f:
        return sum(1 for _ in f)


def _round_run(
    config, worker, args, raw_dir, backend_dir, closed_url
) -> tuple[dict, dict]:
    """One worker run in one configuration. Returns (worker output, delivery record)."""
    sink = raw_dir / f"{args[0].stem}.events.jsonl"
    backend = Backend(backend_dir) if config == "http" else None
    try:
        env = config_env(config, sink, backend.url if backend else "", closed_url)
        _run_worker(command(config, worker, *args), env, raw_dir)
        delivered = None
        if config in ("file", "file+sqlcomment"):
            delivered = _count_lines(sink)
        elif backend is not None:
            delivered = backend.event_count()
    finally:
        if backend is not None:
            backend.close()
    if sink.exists():
        sink.unlink()  # can be large; the count is what is kept
    return json.loads(args[0].read_text(encoding="utf-8")), {"delivered": delivered}


def _compare(per_round: dict, configs, value_key: str) -> dict:
    """Paired comparisons of every configuration against base."""
    out = {}
    base = per_round["base"]
    for config in configs:
        if config == "base":
            continue
        rows = per_round[config]
        added_p50 = stats.paired_difference(
            [r["p50_us"] for r in base], [r["p50_us"] for r in rows]
        )
        added_p99 = stats.paired_difference(
            [r["p99_us"] for r in base], [r["p99_us"] for r in rows]
        )
        throughput = stats.paired_percent_change(
            [r[value_key] for r in base], [r[value_key] for r in rows]
        )
        out[config] = {
            "added_p50_us": added_p50,
            "added_p99_us": added_p99,
            "throughput_change_pct": throughput,
            # P5.1: the fixed cost per call that throughput implies,
            # 1e6/throughput_instrumented - 1e6/throughput_base, paired by round.
            "implied_added_us": stats.paired_difference(
                [1e6 / r[value_key] for r in base], [1e6 / r[value_key] for r in rows]
            ),
            "latency_verdict": stats.latency_verdict(added_p99, LATENCY_TARGET_US),
            "throughput_verdict": stats.throughput_verdict(
                throughput, THROUGHPUT_TARGET_PCT
            ),
        }
    return out


def attribution(rounds: dict, components=COMPONENTS) -> list[dict]:
    """Split the added cost into COMPONENTS, two ways, each with a bootstrap CI:
    by per-round p50 latency, and by the per-call cost throughput implies."""
    out = []
    for name, config, minus in components:
        if config not in rounds or minus not in rounds:
            continue
        a, b = rounds[config], rounds[minus]
        out.append(
            {
                "component": name,
                "measured_as": f"{config} − {minus}" if minus != "base" else config,
                "p50_us": stats.paired_difference(
                    [r["p50_us"] for r in b], [r["p50_us"] for r in a]
                ),
                "implied_us": stats.paired_difference(
                    [1e6 / r["per_s"] for r in b], [1e6 / r["per_s"] for r in a]
                ),
            }
        )
    return out


def _round_stats(output: dict, calls: int) -> dict:
    ns = output["ns"]
    return {
        "p50_us": stats.percentile(ns, 50) / 1000,
        "p99_us": stats.percentile(ns, 99) / 1000,
        "per_s": calls / (output["elapsed_ns"] / 1e9),
    }


def postgres(mode: Mode, out_dir: pathlib.Path, closed_url: str, log=print) -> dict:
    raw = out_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    samples = {c: {t.name: [] for t in TIERS} for c in CONFIGS}
    per_round = {c: {t.name: [] for t in TIERS} for c in CONFIGS}
    delivery = {c: [] for c in CONFIGS}
    expected_events = sum((mode.warmup + mode.calls) * t.events_per_call for t in TIERS)
    for r in range(mode.rounds):
        for config in CONFIGS:
            out_file = raw / f"pg-{config}-r{r}.json"
            output, delivered = _round_run(
                config,
                PG_WORKER,
                [out_file, mode.warmup, mode.calls],
                raw,
                out_dir / "backend" / f"pg-r{r}",
                closed_url,
            )
            for tier in TIERS:
                samples[config][tier.name] += output[tier.name]["ns"]
                per_round[config][tier.name].append(
                    _round_stats(output[tier.name], mode.calls)
                )
            if config != "base":
                delivery[config].append(delivered["delivered"])
            log(f"  postgres round {r + 1}/{mode.rounds} {config}")
    profile = _profile_round(mode, out_dir, closed_url, log)
    tiers = {}
    for tier in TIERS:
        rounds = {c: per_round[c][tier.name] for c in CONFIGS}
        tiers[tier.name] = {
            "label": tier.label,
            "latency_us": {
                c: stats.summarize(samples[c][tier.name], 1000) for c in CONFIGS
            },
            "throughput_per_s": {
                c: stats.summarize([r["per_s"] for r in rounds[c]]) for c in CONFIGS
            },
            "versus_base": _compare(rounds, CONFIGS, "per_s"),
            "rounds": rounds,
            "attribution": attribution(rounds),
        }
    return {
        "tiers": tiers,
        "delivery": {
            c: {
                "expected_per_round": 0 if c == "wrap-only" else expected_events,
                "delivered_per_round": delivery[c],
                **({"note": NO_DELIVERY[c]} if c in NO_DELIVERY else {}),
            }
            for c in CONFIGS
            if c != "base"
        },
        "profile": profile,
    }


def _profile_round(mode: Mode, out_dir: pathlib.Path, closed_url: str, log) -> dict:
    """One extra round per instrumented configuration, under cProfile, on
    PROFILE_TIERS only. Attribution only: no timing from it is ever used."""
    from overhead import profiling

    raw = out_dir / "raw" / "profile"
    raw.mkdir(parents=True, exist_ok=True)
    out = {"tiers": list(PROFILE_TIERS), "top": profiling.TOP, "configs": {}}
    for config in CONFIGS:
        if config == "base":
            continue
        prefix = raw / f"pg-{config}"
        _round_run(
            config,
            PG_WORKER,
            [
                raw / f"pg-{config}.json",
                mode.warmup,
                mode.calls,
                "--profile",
                prefix,
                "--tiers",
                ",".join(PROFILE_TIERS),
            ],
            raw,
            out_dir / "backend" / "pg-profile",
            closed_url,
        )
        out["configs"][config] = {
            tier: profiling.summarize_file(f"{prefix}.{tier}.prof", mode.calls)
            for tier in PROFILE_TIERS
        }
        log(f"  postgres profiling round {config}")
    return out


def kafka(mode: Mode, out_dir: pathlib.Path, log=print) -> dict:
    raw = out_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    samples = {c: [] for c in KAFKA_CONFIGS}
    per_round = {c: [] for c in KAFKA_CONFIGS}
    delivery = {c: [] for c in KAFKA_CONFIGS}
    for r in range(mode.rounds):
        for config in KAFKA_CONFIGS:
            out_file = raw / f"kafka-{config}-r{r}.json"
            output, delivered = _round_run(
                config,
                KAFKA_WORKER,
                [out_file, mode.kafka_warmup, mode.kafka_messages],
                raw,
                out_dir / "backend" / f"kafka-r{r}",
                "",
            )
            samples[config] += output["ns"]
            row = _round_stats(output, mode.kafka_messages)
            row["flush_ms"] = output["flush_ns"] / 1e6
            per_round[config].append(row)
            if config != "base":
                delivery[config].append(delivered["delivered"])
            log(f"  kafka round {r + 1}/{mode.rounds} {config}")
    return {
        "message_bytes": 1024,
        "latency_us": {c: stats.summarize(samples[c], 1000) for c in KAFKA_CONFIGS},
        "throughput_per_s": {
            c: stats.summarize([r["per_s"] for r in per_round[c]])
            for c in KAFKA_CONFIGS
        },
        "versus_base": _compare(per_round, KAFKA_CONFIGS, "per_s"),
        "rounds": per_round,
        "attribution": attribution(per_round, KAFKA_COMPONENTS),
        "delivery": {
            c: {
                "expected_per_round": (
                    0 if c == "wrap-only" else mode.kafka_warmup + mode.kafka_messages
                ),
                "delivered_per_round": delivery[c],
                **({"note": NO_DELIVERY[c]} if c in NO_DELIVERY else {}),
            }
            for c in KAFKA_CONFIGS
            if c != "base"
        },
    }


IMPORTS_BOTH = "import psycopg, confluent_kafka"


def startup(mode: Mode, out_dir: pathlib.Path) -> dict:
    """Interpreter start-up, outside per-call timing: plain, under dcp-instrument, and
    the instrumented child alone (DCP's sitecustomize, without the wrapper process)."""
    from dcp.instrument import instrumented_env

    sink = out_dir / "startup.events.jsonl"
    plain_env = run_live.clean_env()
    dcp_env = dict(plain_env, DCP_EMIT="file://" + str(sink))
    variants = {
        "python": ([sys.executable, "-c", "pass"], plain_env),
        "dcp-instrument python": (
            [sys.executable, "-m", "dcp.instrument", sys.executable, "-c", "pass"],
            dcp_env,
        ),
        "python with DCP's sitecustomize": (
            [sys.executable, "-c", "pass"],
            instrumented_env(dcp_env),
        ),
        # Added in P5.1: a program that does import the libraries DCP patches.
        "python, importing psycopg and confluent_kafka (added in P5.1)": (
            [sys.executable, "-c", IMPORTS_BOTH],
            plain_env,
        ),
        "dcp-instrument python, importing psycopg and confluent_kafka (added in P5.1)": (
            [
                sys.executable,
                "-m",
                "dcp.instrument",
                sys.executable,
                "-c",
                IMPORTS_BOTH,
            ],
            dcp_env,
        ),
    }
    times = {name: [] for name in variants}
    for _ in range(mode.startup_reps):
        for name, (cmd, env) in variants.items():
            t0 = time.perf_counter_ns()
            subprocess.run(cmd, env=env, check=True, capture_output=True, timeout=120)
            times[name].append(time.perf_counter_ns() - t0)
    return {
        "reps": mode.startup_reps,
        "ms": {name: stats.summarize(ns, 1e6) for name, ns in times.items()},
    }


def backpressure(mode: Mode, out_dir: pathlib.Path, closed_url: str) -> dict:
    out_file = out_dir / "raw" / "backpressure.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(BACKPRESSURE_WORKER),
        str(out_file),
        closed_url,
        str(BACKPRESSURE_QUEUE),
        str(mode.warmup),
        str(mode.calls),
    ]
    _run_worker(cmd, run_live.clean_env(), out_file.parent)
    output = json.loads(out_file.read_text(encoding="utf-8"))
    latency = stats.summarize(output["ns"], 1000)
    return {
        "queue_size": output["queue_size"],
        "calls": mode.calls,
        "events_emitted": output["events_emitted"],
        "dropped": output["dropped"],
        "latency_us": latency,
        "bound_ms": BACKPRESSURE_BACKOFF_MS,
        "bounded": latency["max"] < BACKPRESSURE_BACKOFF_MS * 1000,
    }


def run(out_dir: pathlib.Path, quick: bool, log=print) -> dict:
    reason = unavailable()
    if reason:
        raise run_live.LiveUnavailable(reason)
    mode = QUICK if quick else FULL
    out_dir.mkdir(parents=True, exist_ok=True)
    log("  seeding")
    run_live.seed(extra_topics=[KAFKA_TOPIC])
    closed = reserve_closed_port()
    closed_url = f"http://127.0.0.1:{closed.getsockname()[1]}"
    try:
        results = {
            "mode": asdict(mode),
            "configs": list(CONFIGS),
            "kafka_configs": list(KAFKA_CONFIGS),
            "added_in_p51": {
                "configs": list(ADDED_IN_P51),
                "tiers": [t.name for t in TIERS if t.literal],
            },
            "targets": {
                "added_p99_us": LATENCY_TARGET_US,
                "throughput_loss_pct": THROUGHPUT_TARGET_PCT,
            },
            "postgres": postgres(mode, out_dir, closed_url, log),
            "kafka": kafka(mode, out_dir, log),
            "startup": startup(mode, out_dir),
            "backpressure": backpressure(mode, out_dir, closed_url),
        }
    finally:
        closed.close()
    return results
