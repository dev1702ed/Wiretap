"""DCP — transport-layer data lineage.

Public surface is deliberately tiny. The adoption bar is two lines:

    import dcp
    dcp.init(emit="console")
    dcp.patch_psycopg()
"""

from dcp.config import init, shutdown
from dcp.interceptors.kafka import patch_kafka
from dcp.interceptors.postgres import patch_psycopg

__all__ = ["init", "patch_kafka", "patch_psycopg", "shutdown"]
__version__ = "0.1.0.dev0"
