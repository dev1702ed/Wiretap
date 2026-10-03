"""JSONL file emitter. P3; asynchronous by default since P5.1 (O3). Used by
the benchmarks as the event of record.

    file://events.jsonl          asynchronous (the default since P5.1)
    file://events.jsonl?sync=1   synchronous: written before emit() returns

One event per line, in emit() order, never interleaved.

Asynchronous (default): emit() hands the event to a bounded queue; a
background thread serialises, writes and flushes it. That keeps the write
off the caller's thread, as emitters/__init__.py requires of every sink, and
follows the HTTP emitter's pattern: a full queue drops the event and counts it
(never blocks), the worker is re-armed after os.fork(), and dcp.init()
registers shutdown() with atexit, which drains the queue. A process that exits
normally, or dies of an uncaught exception, leaves every event in the file. A
process killed outright (SIGKILL, os._exit) can lose the events still queued.

Synchronous (`?sync=1`, P3's behaviour): each line is written and flushed to
the OS before emit() returns, so a process killed outright still leaves every
event it emitted in the file. For anyone who needs write-before-return.

No fsync in either mode: that guards against a machine crash, not a process
crash, and costs far more.
"""

import json
import queue
import threading
import time

from dcp.emitters.base import DropCounter, Emitter, track_fork

QUEUE_SIZE = 10_000
BATCH_SIZE = 500


class FileEmitter(Emitter):
    def __init__(self, path: str, sync: bool = False, queue_size: int = QUEUE_SIZE):
        if queue_size < 1:
            raise ValueError("queue_size must be at least 1")  # 0 would be unbounded
        self.path = path
        self.sync = sync
        self.queue_size = queue_size
        self._drops = DropCounter("file")
        self._lock = threading.Lock()
        # Held open for the emitter's lifetime; closed by close().
        self._file = open(path, "a", encoding="utf-8")  # noqa: SIM115
        if not sync:
            self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
            self._stop = threading.Event()
            self._start_worker()
        track_fork(self)

    def _start_worker(self) -> None:
        self._worker = threading.Thread(target=self._run, name="dcp-file-emitter", daemon=True)
        self._worker.start()

    def _after_fork_in_child(self) -> None:
        """Re-arm in a child of os.fork(). Another thread may have held a lock at
        fork time. Queued lines belong to the parent, which writes them; writing
        them here too would duplicate them, so the child starts empty."""
        self._lock = threading.Lock()
        self._drops.reset_lock()
        if self.sync:
            return
        closed = self._stop.is_set()
        self._queue = queue.Queue(maxsize=self.queue_size)
        self._stop = threading.Event()
        if closed:
            self._stop.set()
        else:
            self._start_worker()

    @property
    def dropped(self) -> int:
        return self._drops.value

    def emit(self, event) -> None:
        if self.sync:
            self._write([event])
            return
        if self._stop.is_set():
            self._drops.add(1, "emitter closed")
            return
        try:
            # The event itself: DCP's events are immutable once built, so it
            # serialises to the same line on the worker thread.
            self._queue.put_nowait(event)
        except queue.Full:
            self._drops.add(1, "queue full")

    def _write(self, events: list) -> None:
        lines = "".join(json.dumps(event.to_dict()) + "\n" for event in events)
        with self._lock:
            try:
                self._file.write(lines)
                self._file.flush()
            except (OSError, ValueError) as exc:  # ValueError: write after close()
                self._drops.add(len(events), repr(exc))

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                lines = [self._queue.get(timeout=0.1)]
            except queue.Empty:
                continue
            while len(lines) < BATCH_SIZE:
                try:
                    lines.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            try:
                self._write(lines)
            finally:
                for _ in lines:
                    self._queue.task_done()

    def flush(self, timeout: float = 5.0) -> None:
        """Wait up to `timeout` seconds for every queued line to be written."""
        if not self.sync:
            deadline = time.monotonic() + timeout
            with self._queue.all_tasks_done:
                while self._queue.unfinished_tasks and self._worker.is_alive():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    self._queue.all_tasks_done.wait(remaining)
        with self._lock:
            if not self._file.closed:
                self._file.flush()

    def close(self, timeout: float = 5.0) -> None:
        """Write what is queued, stop the worker, close the file."""
        if not self.sync:
            self.flush(timeout)
            self._stop.set()
            self._worker.join(timeout)
            left = []
            while True:
                try:
                    left.append(self._queue.get_nowait())
                except queue.Empty:
                    break
                self._queue.task_done()
            if left:
                self._write(left)  # the worker is gone: write them here
        with self._lock:
            self._file.close()
