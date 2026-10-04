"""DCP — transport-layer data lineage.

Public surface is deliberately tiny. The adoption bar is two lines:

    import dcp
    dcp.init(emit="console")
    dcp.patch_psycopg()

The names below are imported on first use (P5.1, A5), so `import dcp`, and
the `dcp-instrument` wrapper process, load nothing they do not need.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dcp.config import init, shutdown
    from dcp.interceptors.kafka import patch_kafka
    from dcp.interceptors.postgres import patch_psycopg
    from dcp.interceptors.threads import patch_threadpool

__all__ = ["init", "patch_kafka", "patch_psycopg", "patch_threadpool", "shutdown"]
__version__ = "0.1.0"

_EXPORTS = {
    "init": "dcp.config",
    "shutdown": "dcp.config",
    "patch_kafka": "dcp.interceptors.kafka",
    "patch_psycopg": "dcp.interceptors.postgres",
    "patch_threadpool": "dcp.interceptors.threads",
}


def __getattr__(name: str):
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module 'dcp' has no attribute {name!r}")
    import importlib

    value = getattr(importlib.import_module(module), name)
    globals()[name] = value  # resolved once
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))
