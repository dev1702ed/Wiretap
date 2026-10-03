"""Process-level setup. P1.

Captures job identity ONCE at init (spec/README.md decision #4) and wires
the emitter. Nothing here touches the hot path.
"""

import atexit
import os
import socket
import sys
from dataclasses import dataclass
from urllib.parse import urlsplit


@dataclass(frozen=True)
class JobIdentity:
    """Who is moving the data. Captured once; reused on every event.

    This is what lights up the dark zones: an ad-hoc script has no framework
    plugin reporting it, but it does have a pid, a host, and a name.
    """

    name: str
    host: str
    pid: int


_job: JobIdentity | None = None
_emitter = None
_propagate_sql = False
_capture = True


def init(
    emit: str = "console",
    job_name: str | None = None,
    propagate_sql: bool = False,
    capture: bool = True,
) -> None:
    """Initialise DCP for this process.

    Args:
        emit: sink spec — "console"; "file://path" (JSONL, the event of record);
              "http://host:port" (the DCP backend). "marquez://host:port" raises
              NotImplementedError pointing at the batch OpenLineage bridge
              (bridges/openlineage); "null://" builds every event and discards
              it, a diagnostic that records nothing (emitters/null.py);
              anything else raises ValueError.
        job_name: override the inferred script name.
        propagate_sql: append a trace comment to outbound SQL (spec §3). Off by
              default: it is DCP's one modification of traffic.
        capture: False installs nothing new but makes every patched call skip
              capture entirely (no parsing, no events, no SQL comment): the
              wrappers stay in place and call straight through. An operational
              kill switch, and the benchmark's `wrap-only` measurement
              (dcp-instrument reads it from DCP_CAPTURE=off).

    The file and HTTP sinks buffer, so shutdown() is registered with atexit: a
    script that never calls dcp.shutdown() still delivers its events.
    """
    global _job, _emitter, _propagate_sql, _capture
    emitter = _make_emitter(emit)  # first, so a bad spec changes nothing
    previous = _emitter
    _emitter = emitter
    _propagate_sql = propagate_sql
    _capture = bool(capture)
    _job = JobIdentity(
        name=job_name or os.path.basename(sys.argv[0]) or "<interactive>",
        host=socket.gethostname(),
        pid=os.getpid(),
    )
    close = getattr(previous, "close", None)
    if close is not None:
        close()  # re-init: deliver what the old sink holds, release its thread/file
    if emit not in ("console", "null://"):
        _register_shutdown()


def _make_emitter(emit: str):
    if emit == "console":
        from dcp.emitters.console import ConsoleEmitter

        return ConsoleEmitter()
    if emit == "null://":
        from dcp.emitters.null import NullEmitter

        return NullEmitter()
    if emit.startswith("file://"):
        from dcp.emitters.file import FileEmitter

        path = emit.removeprefix("file://")
        if not path:
            raise ValueError("file:// sink needs a path, e.g. file://events.jsonl")
        return FileEmitter(path)
    if emit.startswith("http://"):
        from dcp.emitters.http import HTTPEmitter

        parts = urlsplit(emit)
        # Reading .port raises ValueError for a malformed port, as promised above.
        if not parts.hostname or parts.port == 0:
            raise ValueError(f"http:// sink needs a host, e.g. http://localhost:8000: {emit!r}")
        return HTTPEmitter(emit)
    if emit.startswith("marquez://"):
        raise NotImplementedError(
            "there is no live marquez:// sink. Emit with file://dcp_events.jsonl, then run "
            "the batch bridge: python -m dcp_openlineage --events dcp_events.jsonl "
            "--post http://localhost:5000 (see bridges/openlineage)"
        )
    raise ValueError(
        f"unknown emitter sink {emit!r}: expected console, file://path, http://host:port or null://"
    )


_shutdown_registered = False


def _register_shutdown() -> None:
    global _shutdown_registered
    if not _shutdown_registered:
        atexit.register(shutdown)
        _shutdown_registered = True


def current_emitter():
    if _emitter is None:
        raise RuntimeError("dcp.init() must be called before instrumenting")
    return _emitter


def shutdown(timeout: float = 5.0) -> None:
    """Flush buffered events. Safe to call twice."""
    if _emitter is not None:
        _emitter.flush(timeout=timeout)


def current_job() -> JobIdentity:
    if _job is None:
        raise RuntimeError("dcp.init() must be called before instrumenting")
    return _job


def sql_propagation_enabled() -> bool:
    """Whether outbound SQL carries a trace comment. Off unless init() opts in."""
    return _propagate_sql


def capture_enabled() -> bool:
    """Whether patched calls capture. True unless init(capture=False): the kill switch."""
    return _capture
