"""DCP's start-up hook for dcp-instrument. P5.

dcp-instrument puts this file's directory first on PYTHONPATH, so Python's
`site` module imports it at interpreter start-up, before any user import. It:

1. calls dcp.init() from DCP_EMIT, DCP_JOB_NAME, DCP_PROPAGATE_SQL and
   DCP_CAPTURE;
2. patches psycopg, confluent-kafka and ThreadPoolExecutor, each only if its
   library is importable;
3. runs the sitecustomize this one shadows, if there is one further along
   sys.path (Debian and Ubuntu ship one, for example).

Monitor-only: a DCP failure in steps 1-2 is caught and logged at debug, and
the program runs uninstrumented. An error raised by the chained sitecustomize
is left alone, so Python reports it exactly as it would without DCP.

Keep this directory free of other modules: everything in it becomes
importable by top-level name in the instrumented program.
"""

import logging
import os
import sys

_log = logging.getLogger("dcp")
_HERE = os.path.dirname(os.path.realpath(__file__))


def _job_name() -> str | None:
    """DCP_JOB_NAME, else the script's basename (dcp.init's default).

    Under `python -m pkg.mod`, sys.argv[0] is still "-m" at start-up, so the
    module name is taken from sys.orig_argv instead.
    """
    name = os.environ.get("DCP_JOB_NAME")
    if name:
        return name
    if sys.argv[:1] == ["-m"]:
        orig = list(getattr(sys, "orig_argv", []))
        if "-m" in orig and orig.index("-m") + 1 < len(orig):
            return orig[orig.index("-m") + 1]
    return None


def capture_off(value: str | None) -> bool:
    """DCP_CAPTURE=off (or 0, false, no; any case) is the kill switch."""
    return (value or "").strip().lower() in ("off", "0", "false", "no")


def _start_dcp() -> None:
    import importlib.util

    import dcp

    dcp.init(
        emit=os.environ.get("DCP_EMIT") or "console",
        job_name=_job_name(),
        propagate_sql=os.environ.get("DCP_PROPAGATE_SQL") == "1",
        capture=not capture_off(os.environ.get("DCP_CAPTURE")),
    )
    for module, patch in (("psycopg", dcp.patch_psycopg), ("confluent_kafka", dcp.patch_kafka)):
        try:
            if importlib.util.find_spec(module) is not None:
                patch()
        except Exception:  # noqa: BLE001 — monitor-only: one library must not block the others
            _log.debug("dcp-instrument could not patch %s", module, exc_info=True)
    dcp.patch_threadpool()


def _chain() -> None:
    """Run the next sitecustomize on sys.path, the one this file shadows."""
    import importlib.machinery
    import importlib.util

    rest = [p for p in sys.path if os.path.realpath(p or os.curdir) != _HERE]
    spec = importlib.machinery.PathFinder.find_spec("sitecustomize", rest)
    if spec is None or spec.loader is None:
        return
    if spec.origin and os.path.dirname(os.path.realpath(spec.origin)) == _HERE:
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules["sitecustomize"] = module  # later `import sitecustomize` sees theirs
    spec.loader.exec_module(module)


try:
    _start_dcp()
except Exception:  # noqa: BLE001 — monitor-only: the program must run regardless
    _log.debug("dcp-instrument could not start DCP; running uninstrumented", exc_info=True)

_chain()
