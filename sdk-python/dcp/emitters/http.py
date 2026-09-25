"""HTTP emitter → the DCP backend. P3.

Background thread + bounded queue. On queue-full the correct behaviour is an
open question with real consequences: dropping breaks the graph in a way it
does not break tracing, since a dropped edge disconnects it. Leaning: block
briefly, then drop with a loud counter — never silently.
"""

from dcp.emitters.base import Emitter


class HTTPEmitter(Emitter):
    def __init__(self, endpoint: str, queue_size: int = 10_000):
        self.endpoint = endpoint
        self.queue_size = queue_size

    def emit(self, event) -> None:
        raise NotImplementedError("P3")

    def flush(self, timeout: float = 5.0) -> None:
        raise NotImplementedError("P3")
