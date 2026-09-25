"""JSONL file emitter. P1. Used by the benchmarks as the event of record."""

from dcp.emitters.base import Emitter


class FileEmitter(Emitter):
    def __init__(self, path: str):
        self.path = path

    def emit(self, event) -> None:
        raise NotImplementedError("P1")

    def flush(self, timeout: float = 5.0) -> None:
        raise NotImplementedError("P1")
