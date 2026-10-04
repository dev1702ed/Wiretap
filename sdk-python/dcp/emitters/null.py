"""Null emitter: a diagnostic sink. P5.1.

    DCP_EMIT=null://        (or dcp.init(emit="null://"))

Every event is captured and constructed exactly as for a real sink, then
discarded: emit() does nothing with it, not even serialise it. Running a
program with this sink measures capture and event construction while
excluding delivery, which is how the overhead benchmark's `capture-null`
configuration isolates the sinks' own cost. It records nothing, so it is never
a production sink.
"""

from dcp.emitters.base import Emitter


class NullEmitter(Emitter):
    def emit(self, event) -> None:
        return None

    def flush(self, timeout: float = 5.0) -> None:
        return None
