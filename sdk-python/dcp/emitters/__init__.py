"""Emitters — where events go once observed.

Hard requirement: emission is async and non-blocking. If the emitter ever
blocks the intercepted call, the overhead budget (< 1 ms p99) is gone and the
headline claim goes with it.
"""

from dcp.emitters.base import Emitter

__all__ = ["Emitter"]
