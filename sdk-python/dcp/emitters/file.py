"""JSONL file emitter. P3. Used by the benchmarks as the event of record.

One event per line. A lock serialises writes, so lines from concurrent threads
never interleave. Each line is flushed to the OS as it is written, so a script
that dies mid-run still leaves every event it emitted in the file. No fsync:
that guards against a machine crash, not a process crash, and costs far more.
"""

import json
import threading

from dcp.emitters.base import DropCounter, Emitter, track_fork


class FileEmitter(Emitter):
    def __init__(self, path: str):
        self.path = path
        self._drops = DropCounter("file")
        self._lock = threading.Lock()
        # Held open for the emitter's lifetime; closed by close().
        self._file = open(path, "a", encoding="utf-8")  # noqa: SIM115
        track_fork(self)

    def _after_fork_in_child(self) -> None:
        """Another thread may have held the lock at fork time. Every line is
        flushed as written, so the child inherits no buffered events."""
        self._lock = threading.Lock()
        self._drops.reset_lock()

    @property
    def dropped(self) -> int:
        return self._drops.value

    def emit(self, event) -> None:
        line = json.dumps(event.to_dict()) + "\n"
        with self._lock:
            try:
                self._file.write(line)
                self._file.flush()
            except (OSError, ValueError) as exc:  # ValueError: emit after close()
                self._drops.add(1, repr(exc))

    def flush(self, timeout: float = 5.0) -> None:
        with self._lock:
            if not self._file.closed:
                self._file.flush()

    def close(self) -> None:
        with self._lock:
            self._file.close()
