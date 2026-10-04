"""Time the dark-zone demo, cold and warm, and write its own record. P5.2 (D2, step 7).

    python examples/dark-zone/time_demo.py [--out docs/results/demo-local.md]
        [--skip-cold] [--timeout 900] [--down]

Run by `examples/dark-zone/time-demo.ps1` on the owner's machine (docs/RUNBOOK.md,
step 7). From the repository root, with Docker running:

1. **Cold**: `docker compose down -v`, then remove the demo's images (an image
   another container still uses, such as `postgres:16` under your own
   `dcp-postgres`, stays; the record lists what was present), then time
   `docker compose up -d --build` until Marquez shows both jobs linked through
   `enriched_orders`. Docker's build cache is not cleared.
2. **Warm**: `docker compose down -v` (images kept), then the same timing.

"Linked through enriched_orders" is checked through Marquez's API, not by eye:
`nightly_enrich.py`'s outputs and `warehouse_loader.py`'s inputs must both name
the dataset `enriched_orders` in namespace `kafka://kafka:9092`. The record
(`docs/results/demo-local.md`) holds the cold and warm seconds, the check's
result, the demo container's exit code, the image tags and IDs, and the UTC
timestamp, all written by this script. No number in it is typed by hand.

The stack is left running so the graph can be looked at
(http://localhost:3000); `--down` removes it at the end. Standard library only.
"""

import argparse
import datetime
import json
import os
import pathlib
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
COMPOSE = "examples/dark-zone/docker-compose.yml"
MARQUEZ = "http://localhost:5000"
NAMESPACE = "dcp://dark-zone-demo"
PRODUCER, CONSUMER = "nightly_enrich.py", "warehouse_loader.py"
TOPIC = ("kafka://kafka:9092", "enriched_orders")
BAR_S = 300  # the v1 bar: under 5 minutes


def compose(*args: str) -> list[str]:
    return ["docker", "compose", "-f", COMPOSE, *args]


def run(command: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command from the repository root, capturing its output."""
    return subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, check=check
    )


# --- The Marquez API check -------------------------------------------------------


def _get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def check_marquez(base: str = MARQUEZ) -> dict:
    """Whether Marquez shows both jobs, linked through enriched_orders.

    Returns {"jobs": [...], "producer_outputs": [...], "consumer_inputs": [...],
    "linked": bool}. Never raises on an unreachable or incomplete API: that is
    just "not linked yet".
    """
    ns = urllib.parse.quote(NAMESPACE, safe="")
    result = {
        "jobs": [],
        "producer_outputs": [],
        "consumer_inputs": [],
        "linked": False,
    }
    try:
        jobs = _get(f"{base}/api/v1/namespaces/{ns}/jobs").get("jobs", [])
        result["jobs"] = sorted(job["name"] for job in jobs)
        if not {PRODUCER, CONSUMER} <= set(result["jobs"]):
            return result
        producer = _get(
            f"{base}/api/v1/namespaces/{ns}/jobs/{urllib.parse.quote(PRODUCER)}"
        )
        consumer = _get(
            f"{base}/api/v1/namespaces/{ns}/jobs/{urllib.parse.quote(CONSUMER)}"
        )
    except (OSError, ValueError, KeyError, urllib.error.URLError):
        return result

    def ids(datasets):
        return sorted((d["namespace"], d["name"]) for d in datasets or [])

    result["producer_outputs"] = ids(producer.get("outputs"))
    result["consumer_inputs"] = ids(consumer.get("inputs"))
    result["linked"] = (
        TOPIC in result["producer_outputs"] and TOPIC in result["consumer_inputs"]
    )
    return result


def wait_until_linked(
    base, timeout_s, clock=time.monotonic, sleep=time.sleep, check=check_marquez
):
    """Poll Marquez every 2 s until linked. Returns (seconds waited, last check)."""
    start = clock()
    while True:
        last = check(base)
        elapsed = clock() - start
        if last["linked"] or elapsed > timeout_s:
            return elapsed, last
        sleep(2)


# --- One timed run ---------------------------------------------------------------


def images() -> list[str]:
    out = run(compose("config", "--images")).stdout
    return sorted({line.strip() for line in out.splitlines() if line.strip()})


def present(image: str) -> bool:
    return run(["docker", "image", "inspect", image], check=False).returncode == 0


def image_id(image: str) -> str:
    out = run(["docker", "image", "inspect", "--format", "{{.Id}}", image], check=False)
    return out.stdout.strip()[:19] if out.returncode == 0 else "not present"


def demo_exit_code() -> str:
    out = run(
        compose("ps", "-a", "--format", "json", "demo"), check=False
    ).stdout.strip()
    try:
        rows = [json.loads(line) for line in out.splitlines() if line.strip()]
        if len(rows) == 1 and isinstance(rows[0], list):
            rows = rows[0]
        return str(rows[0].get("ExitCode", "unknown")) if rows else "not found"
    except ValueError:
        return "unknown"


def timed_run(kind: str, base: str, timeout_s: float) -> dict:
    """down -v (cold: and remove the demo's images), then time up to linked."""
    run(compose("down", "-v", "--remove-orphans"))
    removed, kept = [], []
    if kind == "cold":
        for image in images():
            if not present(image):
                continue
            gone = run(["docker", "image", "rm", image], check=False).returncode == 0
            (removed if gone else kept).append(image)
    present_before = [image for image in images() if present(image)]
    start = time.monotonic()
    up = run(compose("up", "-d", "--build"), check=False)
    if up.returncode == 0:
        waited, last = wait_until_linked(base, timeout_s)
    else:  # nothing will come up: say why instead of polling until the timeout
        waited, last = 0.0, check_marquez(base)
        print(
            f"   docker compose up failed ({up.returncode}):\n{up.stderr[-2000:]}",
            flush=True,
        )
    seconds = time.monotonic() - start if up.returncode == 0 else None
    # The demo container exits after posting; give it a moment to finish.
    for _ in range(30):
        code = demo_exit_code()
        if code not in ("unknown", "not found", ""):
            break
        time.sleep(1)
    return {
        "kind": kind,
        "seconds": round(seconds, 1)
        if seconds is not None and last["linked"]
        else None,
        "waited": round(waited, 1),
        "up_exit_code": up.returncode,
        "up_error": ""
        if up.returncode == 0
        else (up.stderr or up.stdout).strip()[-300:],
        "demo_exit_code": demo_exit_code(),
        "check": last,
        "removed_images": removed,
        "kept_images": kept,
        "present_before": present_before,
    }


# --- The record ------------------------------------------------------------------


def _git(*args):
    out = run(["git", *args], check=False)
    return out.stdout.strip() if out.returncode == 0 else None


def environment() -> dict:
    docker = run(["docker", "version", "--format", "{{.Server.Version}}"], check=False)
    compose_version = run(["docker", "compose", "version", "--short"], check=False)
    return {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(
            timespec="seconds"
        ),
        "git_commit": _git("rev-parse", "HEAD"),
        "git_dirty": bool(_git("status", "--porcelain")),
        "os": platform.platform(),
        "docker": docker.stdout.strip() or "unknown",
        "compose": compose_version.stdout.strip() or "unknown",
    }


def render_record(env: dict, image_rows: list[dict], runs: list[dict]) -> str:
    def yes(value):
        return "yes" if value else "**no**"

    def cached(r):
        if r["kind"] == "warm":
            return "every image present; containers and volumes removed first"
        kept = ", ".join(f"`{i}`" for i in r["kept_images"]) or "none"
        return (
            f"the demo's images removed first (still present, in use elsewhere: {kept})"
        )

    lines = [
        "# Dark-zone demo: time to first graph (`demo-local`)",
        "",
        (
            "Written by `examples/dark-zone/time_demo.py` (run by `time-demo.ps1`, "
            "docs/RUNBOOK.md step 7). Do not edit by hand: re-run it."
        ),
        "",
        "|  |  |",
        "|---|---|",
        f"| Started (UTC) | {env['timestamp_utc']} |",
        f"| Git commit | `{env['git_commit']}` |",
        f"| Working tree dirty | {env['git_dirty']} |",
        f"| OS | {env['os']} |",
        f"| Docker server | {env['docker']} |",
        f"| Docker Compose | {env['compose']} |",
        f"| Compose file | `{COMPOSE}` |",
        "",
        "## Images",
        "",
        "| Image (tag) | Image ID after the runs |",
        "|---|---|",
        *[f"| `{row['image']}` | `{row['id']}` |" for row in image_rows],
        "",
        "## Timings",
        "",
        (
            "From `docker compose up -d --build` to Marquez showing both jobs linked through "
            f"`enriched_orders` (polled every 2 s). The v1 bar is under {BAR_S} s."
        ),
        "",
        (
            "| Run | Before the run | Seconds to the graph | Under 5 minutes | Demo exit code "
            "| Both jobs linked through `enriched_orders` (Marquez API) |"
        ),
        "|---|---|---|---|---|---|",
    ]
    for r in runs:
        seconds = "not reached" if r["seconds"] is None else f"{r['seconds']:.1f}"
        under = r["seconds"] is not None and r["seconds"] < BAR_S
        lines.append(
            f"| {r['kind']} | {cached(r)} | {seconds} | {yes(under)} | {r['demo_exit_code']} "
            f"| {yes(r['check']['linked'])} |"
        )
    failed = [r for r in runs if r.get("up_exit_code", 0) != 0]
    if failed:
        lines += ["", "## `docker compose up` failed", ""]
        for r in failed:
            lines += [
                f"**{r['kind']}**: exit code {r['up_exit_code']}; the end of its output:",
                "",
                "```",
                r.get("up_error", ""),
                "```",
                "",
            ]
    lines += ["", "## Marquez API check", ""]
    for r in runs:
        c = r["check"]
        lines += [
            f"**{r['kind']}**: jobs in `{NAMESPACE}`: "
            + (", ".join(f"`{j}`" for j in c["jobs"]) or "none")
            + f"; `{PRODUCER}` outputs: "
            + (", ".join(f"`{ns}` `{n}`" for ns, n in c["producer_outputs"]) or "none")
            + f"; `{CONSUMER}` inputs: "
            + (", ".join(f"`{ns}` `{n}`" for ns, n in c["consumer_inputs"]) or "none")
            + ".",
            "",
        ]
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default="docs/results/demo-local.md")
    parser.add_argument("--marquez", default=MARQUEZ)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument(
        "--skip-cold", action="store_true", help="time the warm run only"
    )
    parser.add_argument(
        "--down", action="store_true", help="remove the stack at the end"
    )
    args = parser.parse_args(argv)
    os.chdir(ROOT)
    env = environment()
    runs = []
    for kind in ("warm",) if args.skip_cold else ("cold", "warm"):
        print(f"== {kind} run", flush=True)
        result = timed_run(kind, args.marquez, args.timeout)
        print(
            f"   {result['seconds']} s, linked: {result['check']['linked']}", flush=True
        )
        runs.append(result)
    rows = [{"image": image, "id": image_id(image)} for image in images()]
    out = ROOT / args.out
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(render_record(env, rows, runs))
    print(f"wrote {out}")
    if args.down:
        run(compose("down", "-v"))
    else:
        print(
            "the demo is still up: http://localhost:3000 (namespace dcp://dark-zone-demo)"
        )
    return 0 if all(r["check"]["linked"] for r in runs) else 1


if __name__ == "__main__":
    sys.exit(main())
