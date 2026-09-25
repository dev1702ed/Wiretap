"""Process-level setup. P1.

Captures job identity ONCE at init (spec/README.md open decision #4) and wires
the emitter. Nothing here touches the hot path.
"""

import os
import socket
import sys
from dataclasses import dataclass


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


def init(emit: str = "console", job_name: str | None = None) -> None:
    """Initialise DCP for this process.

    Args:
        emit: sink spec — "console", "file://path", "http://host:port",
              or "marquez://host:port". Only "console" is implemented so far.
        job_name: override the inferred script name.
    """
    global _job, _emitter
    _job = JobIdentity(
        name=job_name or os.path.basename(sys.argv[0]) or "<interactive>",
        host=socket.gethostname(),
        pid=os.getpid(),
    )
    if emit == "console":
        from dcp.emitters.console import ConsoleEmitter
        _emitter = ConsoleEmitter()
    else:
        raise NotImplementedError(f"P3: emitter sink '{emit}' not yet supported")


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
