"""Run the P5 benchmarks and render their results: the ONE command for every number.

    python benchmarks/run.py --label <label> [--quick]
        [--only replay,live,adversarial,scale,overhead,cpu] [--cpu-python PATH ...]

Stages, in order:

    replay       every answer key replayed with faked I/O, scored (score.py)
    live         every answer key live: real Postgres, Kafka, OS processes
    adversarial  cases 1-3 from the live runs, and the OpenLineage baseline check
    scale        P5.1: the GENERATED keys (ground_truth/generated/), replayed, and
                 live where the services are (--quick: one small seed live);
                 scored apart from the hand-written keys
    overhead     4b: live per-call latency and throughput, Kafka, start-up,
                 backpressure (--quick: 5 rounds x 300 calls, else 10 x 2,000)
    cpu          4a: capture's CPU cost with no database, once per Python
                 (--cpu-python, repeatable; default: this interpreter)

Each stage runs if the environment supports it and is skipped otherwise, with
the reason. Raw JSON goes to benchmarks/results/<label>/ (gitignored); the
markdown is rendered to docs/results/P5-<label>.md by render.py, the only code
that writes numbers into markdown. Exits non-zero if any stage failed.

WARNING: the live, adversarial, scale and overhead stages DROP and re-create
the benchmark tables in database `dcp` on localhost:5432 (and, for scale, the
generated keys' `gen_*` tables) and the Kafka topics `enriched_orders`,
`overhead_bench` and `gen_topic_*` on localhost:9092.
"""

import argparse
import datetime
import importlib.metadata
import importlib.util
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid

BENCHMARKS = pathlib.Path(__file__).resolve().parent
ROOT = BENCHMARKS.parent
for _path in (BENCHMARKS / "ground_truth", BENCHMARKS):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

import render
from harness import replay
from live import run_live
from score import score_all, score_workload

RESULTS_DIR = BENCHMARKS / "results"  # raw JSON; gitignored
DOCS_DIR = ROOT / "docs" / "results"  # rendered markdown
STAGES = ("replay", "live", "adversarial", "scale", "overhead", "cpu")
ADVERSARIAL_CASES = (
    (1, "Ad-hoc script", "dark_zone"),
    (2, "Notebook", "notebook"),
    (3, "Shared topic, run-level precision", "topic_fan_in"),
)
PACKAGES = (
    "dcp",
    "dcp-backend",
    "dcp-openlineage",
    "sqlglot",
    "psycopg",
    "psycopg-binary",
    "confluent-kafka",
    "fastapi",
    "uvicorn",
    "nbclient",
    "nbformat",
    "ipykernel",
    "jupyter_client",
    "openlineage-python",
    "networkx",
    "jsonschema",
)
LABEL = re.compile(r"[a-z0-9][a-z0-9-]*")
PIN_FILES = (BENCHMARKS / "requirements.txt", BENCHMARKS / "constraints.txt")
_PIN = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*==\s*([^\s;]+)\s*(?:;\s*(.+))?$"
)
_MARKER = re.compile(r'^python_version\s*(<=|>=|==|!=|<|>)\s*["\']([0-9.]+)["\']$')


def normalize(name: str) -> str:
    """A distribution name as PEP 503 compares it."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split(".") if part.isdigit())


def marker_applies(marker: str | None, python: tuple[int, ...]) -> bool:
    """Whether a pin's environment marker holds. Only `python_version OP "X.Y"`
    is used in the pin files; anything else is reported, not guessed."""
    if not marker:
        return True
    match = _MARKER.match(marker.strip())
    if not match:
        raise ValueError(f"unsupported environment marker in a pin file: {marker!r}")
    op, version = match.groups()
    have, want = python[: len(_version_tuple(version))], _version_tuple(version)
    return {
        "<": have < want,
        "<=": have <= want,
        ">": have > want,
        ">=": have >= want,
        "==": have == want,
        "!=": have != want,
    }[op]


def read_pins(paths=PIN_FILES, python: tuple[int, ...] | None = None) -> dict[str, str]:
    """name -> pinned version, from every `name==version` line that applies to
    this Python. Later files win only where they agree (they must not disagree)."""
    python = python or sys.version_info[:3]
    pins: dict[str, str] = {}
    for path in paths:
        for line in pathlib.Path(path).read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            match = _PIN.match(line)
            if not match:
                continue
            name, _extras, version, marker = match.groups()
            if not marker_applies(marker, python):
                continue
            key = normalize(name)
            if pins.get(key, version) != version:
                raise ValueError(
                    f"{name} is pinned to two versions: {pins[key]} and {version}"
                )
            pins[key] = version
    return pins


def pin_check(pins: dict[str, str], installed) -> dict:
    """Compare installed versions with the pins: a warning, never a failure."""
    mismatches = []
    for name, pinned in sorted(pins.items()):
        have = installed(name)
        if have != pinned:
            mismatches.append({"package": name, "pinned": pinned, "installed": have})
    return {
        "files": [
            str(pathlib.Path(p).relative_to(ROOT)).replace(os.sep, "/")
            for p in PIN_FILES
        ],
        "checked": len(pins),
        "mismatches": mismatches,
    }


def _installed(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def pins_environment(log=None) -> dict:
    try:
        result = pin_check(read_pins(), _installed)
    except (OSError, ValueError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    if log is not None:
        for m in result["mismatches"]:
            log(
                f"warning: {m['package']} is {m['installed'] or 'not installed'}, "
                f"pinned {m['pinned']} (see benchmarks/requirements.txt)"
            )
    return result


def parse_only(text: str | None) -> list[str] | None:
    if not text:
        return None
    names = [name.strip() for name in text.split(",") if name.strip()]
    unknown = [name for name in names if name not in STAGES]
    if unknown:
        raise ValueError(f"unknown stage(s) {unknown}; choose from {', '.join(STAGES)}")
    return names


def probe() -> dict[str, str | None]:
    """What the environment can run: None, or the reason it can't."""

    def missing(module: str, hint: str) -> str | None:
        return None if importlib.util.find_spec(module) else f"missing {module}: {hint}"

    hint = "pip install -r benchmarks/requirements.txt"
    return {
        "live": run_live.unavailable(),
        "openlineage": missing("openlineage", hint),
        "uvicorn": missing("uvicorn", hint),
    }


def blocker(stage: str, probes: dict) -> str | None:
    """Why `stage` can't run here, or None."""
    needs = {
        "replay": (),
        "cpu": (),
        "live": ("live",),
        "adversarial": ("live", "openlineage"),
        "scale": (),  # replay always; its live half is skipped inside, with the reason
        "overhead": ("live", "uvicorn"),
    }[stage]
    for need in needs:
        if probes.get(need):
            return probes[need]
    return None


def plan(only: list[str] | None, probes: dict) -> list[dict]:
    """Every stage, with whether it runs and, if not, why."""
    out = []
    for stage in STAGES:
        if only is not None and stage not in only:
            out.append({"stage": stage, "status": "not requested"})
            continue
        reason = blocker(stage, probes)
        if reason:
            out.append({"stage": stage, "status": "skipped", "reason": reason})
        else:
            out.append({"stage": stage, "status": "run"})
    return out


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def cpu_model() -> str:
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            return winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
        except OSError:
            return platform.processor() or "unknown"
    try:
        for line in pathlib.Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    if sys.platform == "darwin":
        out = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            check=False,
        )
        if out.stdout.strip():
            return out.stdout.strip()
    return platform.processor() or "unknown"


def packages() -> dict[str, str | None]:
    out = {}
    for name in PACKAGES:
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            out[name] = None
    try:
        import confluent_kafka

        out["librdkafka"] = confluent_kafka.libversion()[0]
    except ImportError:
        out["librdkafka"] = None
    return out


def postgres_version() -> str | None:
    try:
        return run_live.postgres_version()
    except Exception as exc:  # noqa: BLE001 — recorded, not fatal: the stage reports why
        return f"unavailable ({type(exc).__name__})"


def environment(argv: list[str], probes: dict, log=None) -> dict:
    status = _git("status", "--porcelain")
    return {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "command": "python benchmarks/run.py " + " ".join(argv),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": None if status is None else bool(status),
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "os": platform.platform(),
        "cpu_model": cpu_model(),
        "cpu_count": os.cpu_count(),
        "ci": os.environ.get("GITHUB_ACTIONS") == "true",
        "postgres_server_version": None if probes.get("live") else postgres_version(),
        "kafka_broker_version": None,
        "kafka_broker_version_note": (
            "not reported to clients by the Kafka protocol; declared: "
            + (os.environ.get("DCP_BENCH_KAFKA_VERSION") or "not declared")
            + " (DCP_BENCH_KAFKA_VERSION)"
        ),
        "packages": packages(),
        "dcp_configuration": {
            "instrumentation": "dcp-instrument (sitecustomize), configured by DCP_* variables",
            "http_emitter": "queue_size=10000, batch_size=500, max_retries=3, backoff=0.5 s",
            "propagate_sql": "off, except the file+sqlcomment configuration",
        },
        "probes": probes,
        "pins": pins_environment(log),
    }


def run_cpu(pythons: list[str], out_dir: pathlib.Path, log) -> dict:
    results = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for index, python in enumerate(pythons):
        out = out_dir / f"cpu-{index}.json"
        log(f"  cpu: {python}")
        try:
            proc = subprocess.run(
                [python, str(BENCHMARKS / "overhead" / "cpu.py"), "--out", str(out)],
                cwd=BENCHMARKS / "overhead",
                env=run_live.clean_env(),
                capture_output=True,
                text=True,
                timeout=7200,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            results.append(
                {"executable": python, "error": f"{type(exc).__name__}: {exc}"}
            )
            continue
        if proc.returncode != 0:
            results.append({"executable": python, "error": proc.stderr[-3000:]})
        else:
            results.append(json.loads(out.read_text(encoding="utf-8")))
    return {"pythons": results}


BASELINE_SUFFIX = "dataset-level baseline"


def perfect(rows: list[dict]) -> bool:
    """Precision and recall 1.0 on every row of DCP's own graph (0/0 counts as
    perfect). The dataset-level baseline rows are the comparison, not DCP's
    graph, and are left out: on topic_fan_in they are meant to fall short."""
    return all(
        row["hits"] == row["found"] == row["expected"]
        for row in rows
        if not row["label"].endswith(BASELINE_SUFFIX)
    )


def row(rows: list[dict], label: str) -> dict | None:
    return next((r for r in rows if r["label"] == label), None)


def evaluate_cases(live: dict, baseline: dict | None) -> list[dict]:
    """Adversarial cases 1-3 from live results, with the baseline measurement."""
    by_name = {w["workload"]: w for w in live["workloads"]}
    cases = []
    for number, title, workload in ADVERSARIAL_CASES:
        w = by_name.get(workload)
        if w is None:
            cases.append(
                {
                    "case": number,
                    "title": title,
                    "workload": workload,
                    "status": "not run",
                }
            )
            continue
        dcp_rows = w["score"]["dcp"]
        case = {
            "case": number,
            "title": title,
            "workload": workload,
            "programs": [p["program"] for p in w["processes"]],
            "dcp_perfect": perfect(dcp_rows),
        }
        if number == 3:
            baseline_row = row(dcp_rows, f"upstream(daily_revenue) {BASELINE_SUFFIX}")
            case["dataset_level_over_approximates"] = bool(
                baseline_row and baseline_row["hits"] < baseline_row["found"]
            )
            case["consumer_checked_record"] = all(
                p["exit_code"] == 0 for p in w["processes"]
            )
            shown = (
                case["dcp_perfect"]
                and case["dataset_level_over_approximates"]
                and case["consumer_checked_record"]
            )
        else:
            shown = case["dcp_perfect"]
            if baseline is not None:
                case["openlineage_events_without_dcp"] = baseline[
                    "events_received_uninstrumented"
                ]
        case["status"] = "demonstrated live" if shown else "NOT demonstrated"
        cases.append(case)
    return cases


def run_adversarial(results: dict, out_dir: pathlib.Path, log) -> dict:
    from adversarial import baseline_check

    live = results.get("live")
    if not live or "workloads" not in live:
        log("  adversarial: running cases 1-3 live")
        live = run_live.run_all(
            out_dir / "live", [workload for _, _, workload in ADVERSARIAL_CASES]
        )
    log("  adversarial: OpenLineage baseline check")
    baseline = baseline_check.run(out_dir / "baseline")
    return {"cases": evaluate_cases(live, baseline), "baseline": baseline}


QUICK_SCALE_LIVE = ("scale_s01",)  # B4: CI's quick mode runs one small seed live


def _rows_agree(a: dict, b: dict) -> bool:
    def key(rows):
        return [(r["label"], r["hits"], r["found"], r["expected"]) for r in rows]

    return all(key(a[s]) == key(b[s]) for s in ("dcp", "openlineage"))


def run_scale(out_dir: pathlib.Path, quick: bool, probes: dict, log) -> dict:
    """P5.1 (B3): every generated key replayed, and live where the services are
    (in quick mode, one small seed). Scored apart from the hand-written keys."""
    import generate as generator
    import scale

    names = generator.generated_names()
    keys = {name: generator.load_generated(name) for name in names}
    log(f"  scale: replaying {len(names)} generated keys")
    replayed, split = {}, {}
    for name in names:
        events = replay(keys[name])
        replayed[name] = score_workload(keys[name], events)
        split[name] = scale.split_jobs(events)
    out = {
        "generator_version": generator.VERSION,
        "replay": {
            "scores": replayed,
            "summary": scale.summarize(keys, replayed, split),
        },
    }
    reason = probes.get("live")
    if reason:
        out["live"] = {"skipped": reason}
        return out
    live_names = [n for n in names if n in QUICK_SCALE_LIVE] if quick else names
    run_id = uuid.uuid4().hex[:8]
    scored, records, live_split = {}, {}, {}
    for name in live_names:
        log(f"  scale: {name} live ({len(keys[name]['processes'])} processes)")
        record, events = run_live.run_workload(
            keys[name],
            out_dir / "live" / name,
            run_id,
            key_path=generator.path_for(name),
        )
        scored[name] = score_workload(keys[name], events)
        live_split[name] = scale.split_jobs(events)
        records[name] = {
            "processes": len(record["processes"]),
            "exit_codes": sorted({p["exit_code"] for p in record["processes"]}),
            "events": sum(p["events"] for p in record["processes"]),
            "manifest_records": len(record["manifest"]),
            "agrees_with_replay": _rows_agree(scored[name], replayed[name]),
        }
    out["live"] = {
        "run_id": run_id,
        "mode": "quick: one small seed" if quick else "full: every generated key",
        "records": records,
        "scores": scored,
        "summary": scale.summarize({n: keys[n] for n in scored}, scored, live_split),
    }
    return out


def run_overhead(out_dir: pathlib.Path, quick: bool, log) -> dict:
    from overhead import latency

    return latency.run(out_dir, quick, log)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else list(argv)
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--label", required=True, help="names the output, e.g. sandbox, ci"
    )
    parser.add_argument("--quick", action="store_true", help="quick overhead mode")
    parser.add_argument(
        "--only", help=f"comma-separated subset of: {', '.join(STAGES)}"
    )
    parser.add_argument(
        "--cpu-python",
        action="append",
        default=[],
        help="interpreter for the cpu stage",
    )
    args = parser.parse_args(argv)
    if not LABEL.fullmatch(args.label):
        parser.error("--label must be lower-case letters, digits and dashes")
    try:
        only = parse_only(args.only)
    except ValueError as exc:
        parser.error(str(exc))

    def log(message: str) -> None:
        print(message, file=sys.stderr, flush=True)

    out_dir = RESULTS_DIR / args.label
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    probes = probe()
    results = {
        "label": args.label,
        "quick": args.quick,
        "environment": environment(argv, probes, log),
        "stages": plan(only, probes),
    }
    failed = False
    for entry in results["stages"]:
        if entry["status"] != "run":
            log(
                f"{entry['stage']}: {entry['status']} {entry.get('reason', '')}".rstrip()
            )
            continue
        stage = entry["stage"]
        log(f"{stage}: running")
        started = time.monotonic()
        try:
            if stage == "replay":
                results["replay"] = {"workloads": score_all(replay)}
            elif stage == "live":
                results["live"] = run_live.run_all(out_dir / "live")
            elif stage == "adversarial":
                results["adversarial"] = run_adversarial(
                    results, out_dir / "adversarial", log
                )
            elif stage == "scale":
                results["scale"] = run_scale(out_dir / "scale", args.quick, probes, log)
            elif stage == "overhead":
                results["overhead"] = run_overhead(
                    out_dir / "overhead", args.quick, log
                )
            elif stage == "cpu":
                results["cpu"] = run_cpu(
                    args.cpu_python or [sys.executable], out_dir / "cpu", log
                )
            entry["status"] = "ran"
        except run_live.LiveUnavailable as exc:
            entry.update(status="skipped", reason=str(exc))
        except Exception:  # noqa: BLE001 — recorded and rendered; the exit code says it failed
            entry.update(status="failed", error=traceback.format_exc()[-4000:])
            failed = True
        entry["seconds"] = round(time.monotonic() - started, 1)
        log(f"{stage}: {entry['status']} ({entry['seconds']} s)")
    results["environment"]["finished_utc"] = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(timespec="seconds")
    raw = out_dir / "results.json"
    raw.write_text(json.dumps(results, indent=1), encoding="utf-8")
    md = DOCS_DIR / f"P5-{args.label}.md"
    with open(md, "w", encoding="utf-8", newline="\n") as f:
        f.write(render.render(results))
    log(f"raw results: {raw}\nrendered:    {md}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
