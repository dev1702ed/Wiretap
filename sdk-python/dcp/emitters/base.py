"""Emitter interface. P1."""

from abc import ABC, abstractmethod


class Emitter(ABC):
    """Sinks implement this. Keep it small — each new sink should be a
    self-contained contribution."""

    @abstractmethod
    def emit(self, event) -> None:
        """Enqueue an event. MUST NOT block the caller."""

    @abstractmethod
    def flush(self, timeout: float = 5.0) -> None:
        """Drain buffered events."""
