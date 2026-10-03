"""Emitter interface. P1."""

import logging
import os
import threading
import weakref
from abc import ABC, abstractmethod

_log = logging.getLogger("dcp")

# Emitters that hold threads or locks, re-armed in the child after os.fork().
# A WeakSet, so tracking an emitter never keeps it alive.
_fork_aware: "weakref.WeakSet" = weakref.WeakSet()


def track_fork(emitter) -> None:
    """Call emitter._after_fork_in_child() in every child of os.fork()."""
    _fork_aware.add(emitter)


def _after_fork_in_child() -> None:
    for emitter in list(_fork_aware):
        try:
            emitter._after_fork_in_child()
        except Exception:  # noqa: BLE001 — monitor-only: never break the forking caller
            _log.debug("dcp could not re-arm an emitter after fork", exc_info=True)


if hasattr(os, "register_at_fork"):  # not on Windows, which has no fork
    os.register_at_fork(after_in_child=_after_fork_in_child)


class Emitter(ABC):
    """Sinks implement this. Keep it small — each new sink should be a
    self-contained contribution."""

    @abstractmethod
    def emit(self, event) -> None:
        """Enqueue an event. MUST NOT block the caller."""

    @abstractmethod
    def flush(self, timeout: float = 5.0) -> None:
        """Drain buffered events."""


class DropCounter:
    """Counts events a sink had to drop. Never silent, never a hot-path cost.

    The count is exact. The warning is logged when the total crosses a power
    of two (1, 2, 4, 8, ...): a sink that is dropping under sustained load
    must not turn logging into the thing that blocks the caller.
    """

    def __init__(self, sink: str) -> None:
        self.sink = sink
        self.value = 0
        self._lock = threading.Lock()

    def reset_lock(self) -> None:
        """After fork: another thread may have held the lock when it happened."""
        self._lock = threading.Lock()

    def add(self, count: int, reason: str) -> None:
        with self._lock:
            before = self.value
            self.value += count
            after = self.value
        if before.bit_length() != after.bit_length():
            _log.warning(
                "dcp %s emitter dropped %d event(s): %s (%d dropped in total)",
                self.sink,
                count,
                reason,
                after,
            )
