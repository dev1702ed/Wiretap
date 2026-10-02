"""HTTP emitter → the DCP backend. P3.

POSTs JSON arrays of events to `{endpoint}/events` from a background daemon
thread, using only the stdlib (urllib): the SDK takes no new dependencies.

Backpressure: emit() never blocks. It hands the event to a bounded queue with
put_nowait; when the queue is full the event is dropped, counted in
`dropped`, and a warning is logged. The P2 stub leaned towards blocking
briefly before dropping, but emitters/__init__.py makes non-blocking a hard
requirement (the < 1 ms p99 budget), so non-blocking wins. Dropping breaks the
graph in a way it does not break tracing — a dropped edge disconnects it — so
drops are counted exactly and never silent.

Delivery: the worker sends whatever is queued, up to `batch_size` events per
POST. A failed POST is retried with exponential backoff and, after
`max_retries` retries, dropped and counted. A 4xx other than 408/429 is not
retried: the backend rejected the batch, and resending it cannot change that.
"""

import http.client
import json
import logging
import queue
import threading
import time
import urllib.error
import urllib.request

from dcp.emitters.base import DropCounter, Emitter, track_fork

_log = logging.getLogger("dcp")

CONTENT_TYPE = "application/json"
_RETRYABLE_4XX = frozenset({408, 429})


def encode_batch(events: list[dict]) -> bytes:
    """The request body: a JSON array of envelopes. The wire contract with POST /events."""
    return json.dumps(events).encode("utf-8")


class HTTPEmitter(Emitter):
    def __init__(
        self,
        endpoint: str,
        queue_size: int = 10_000,
        batch_size: int = 500,
        max_retries: int = 3,
        backoff: float = 0.5,
        timeout: float = 5.0,
    ):
        if queue_size < 1 or batch_size < 1:
            # queue.Queue(maxsize=0) is unbounded: exactly what this must never be.
            raise ValueError("queue_size and batch_size must be at least 1")
        self.endpoint = endpoint.rstrip("/")
        self.url = f"{self.endpoint}/events"
        self.queue_size = queue_size
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.backoff = backoff
        self.timeout = timeout
        self._drops = DropCounter("http")
        self._queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self._stop = threading.Event()
        self._opener = urllib.request.build_opener()
        self._start_worker()
        track_fork(self)

    def _start_worker(self) -> None:
        self._worker = threading.Thread(target=self._run, name="dcp-http-emitter", daemon=True)
        self._worker.start()

    def _after_fork_in_child(self) -> None:
        """Re-arm in a child of os.fork(): only the forking thread survives.

        The queue is replaced, not drained: whatever was queued at fork time
        belongs to the parent, which still sends it. Sending it here too would
        deliver it twice. The locks inside the queue, the stop flag and the
        drop counter are re-created, since another thread may have held one
        at the moment of the fork. A closed emitter stays closed.
        """
        closed = self._stop.is_set()
        self._queue = queue.Queue(maxsize=self.queue_size)
        self._stop = threading.Event()
        self._drops.reset_lock()
        if closed:
            self._stop.set()
        else:
            self._start_worker()

    @property
    def dropped(self) -> int:
        return self._drops.value

    def emit(self, event) -> None:
        """Enqueue without blocking. Drop and count if full or closed."""
        if self._stop.is_set():
            self._drops.add(1, "emitter closed")
            return
        try:
            self._queue.put_nowait(event.to_dict())
        except queue.Full:
            self._drops.add(1, "queue full")

    def flush(self, timeout: float = 5.0) -> None:
        """Wait up to `timeout` seconds for every queued event to be sent or dropped."""
        deadline = time.monotonic() + timeout
        with self._queue.all_tasks_done:
            while self._queue.unfinished_tasks and self._worker.is_alive():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                self._queue.all_tasks_done.wait(remaining)

    def close(self, timeout: float = 5.0) -> None:
        """Flush, stop the worker, and count anything still queued as dropped."""
        self.flush(timeout)
        self._stop.set()
        self._worker.join(timeout)
        left = 0
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
            self._queue.task_done()
            left += 1
        if left:
            self._drops.add(left, "emitter closed before delivery")

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                batch = [self._queue.get(timeout=0.1)]
            except queue.Empty:
                continue
            while len(batch) < self.batch_size:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            try:
                self._send(batch)
            except Exception:  # noqa: BLE001 — the worker must outlive any one batch
                _log.debug("dcp http emitter failed to send a batch", exc_info=True)
                self._drops.add(len(batch), "unexpected error")
            finally:
                for _ in batch:
                    self._queue.task_done()

    def _send(self, batch: list[dict]) -> None:
        """POST one batch, retrying with backoff; count it as dropped if it never lands."""
        body = encode_batch(batch)
        reason = "not sent"
        for attempt in range(self.max_retries + 1):
            if attempt and self._stop.wait(self.backoff * 2 ** (attempt - 1)):
                break  # closing: stop retrying
            request = urllib.request.Request(
                self.url, data=body, headers={"Content-Type": CONTENT_TYPE}, method="POST"
            )
            try:
                with self._opener.open(request, timeout=self.timeout) as response:
                    response.read()
            except urllib.error.HTTPError as exc:
                exc.close()
                reason = f"HTTP {exc.code} from {self.url}"
                if 400 <= exc.code < 500 and exc.code not in _RETRYABLE_4XX:
                    break
            except (OSError, http.client.HTTPException) as exc:
                reason = f"{exc!r} posting to {self.url}"
            else:
                return
        self._drops.add(len(batch), reason)
