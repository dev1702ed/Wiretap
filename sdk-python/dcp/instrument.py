"""dcp-instrument: run a Python program with DCP capture and no code changes. P5.

    dcp-instrument python script.py [args...]

Modelled on opentelemetry-instrument. The command runs as a subprocess, with
the directory holding DCP's sitecustomize.py first on PYTHONPATH. Python
imports sitecustomize at start-up, before any user import, so DCP initialises
and patches psycopg, confluent-kafka and ThreadPoolExecutor before the program
can bind the originals. That also removes patch_kafka()'s import-order hazard.

Configuration is by environment variable, read by sitecustomize in the child:

    DCP_EMIT            sink, as for dcp.init(emit=...)       default: console
    DCP_JOB_NAME        job name                              default: script basename
    DCP_PROPAGATE_SQL   "1" turns on the SQL trace comment    default: off
    DCP_CAPTURE         "off" keeps the patches but skips      default: on
                        capture: the kill switch (P5.1)

The child's exit code is passed through. A child killed by a signal exits
128 + the signal number, as a shell reports it.

Limits: the command's interpreter must have dcp installed, and PYTHONPATH must
be honoured, so `python -I` / `-E` and `-S` run uninstrumented. Every child
process inherits the environment, so a program's own Python subprocesses are
instrumented too.
"""

import os
import shutil
import subprocess
import sys

AUTOINSTRUMENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_autoinstrument")

USAGE = """usage: dcp-instrument COMMAND [ARGS...]

Run COMMAND (usually `python script.py`) with DCP capture, no code changes.
Environment: DCP_EMIT (default console), DCP_JOB_NAME (default: script name),
DCP_PROPAGATE_SQL=1 (opt in to the SQL trace comment), DCP_CAPTURE=off (kill
switch: run with the patches installed but capture nothing)."""


def instrumented_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """A copy of `env` (default os.environ) with DCP's sitecustomize first on PYTHONPATH."""
    env = dict(os.environ if env is None else env)
    existing = [p for p in env.get("PYTHONPATH", "").split(os.pathsep) if p]
    paths = [AUTOINSTRUMENT_DIR] + [p for p in existing if p != AUTOINSTRUMENT_DIR]
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if not args or args[0] in ("-h", "--help"):
        print(USAGE, file=sys.stdout if args else sys.stderr)
        return 0 if args else 2
    # Resolve on PATH ourselves, so `python` finds python.exe on Windows too.
    command = [shutil.which(args[0]) or args[0], *args[1:]]
    try:
        proc = subprocess.Popen(command, env=instrumented_env())
    except OSError as exc:
        print(f"dcp-instrument: cannot run {args[0]!r}: {exc}", file=sys.stderr)
        return 127
    while True:
        try:
            code = proc.wait()
            break
        except KeyboardInterrupt:
            # Ctrl-C reaches the child too; let it decide how to exit.
            continue
    return 128 - code if code < 0 else code


if __name__ == "__main__":
    sys.exit(main())
