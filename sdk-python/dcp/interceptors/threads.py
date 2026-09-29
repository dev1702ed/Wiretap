"""Context propagation into worker threads. P2.

contextvars do not follow work into a ThreadPoolExecutor: each worker starts
from an empty context, so a read in a worker would mint a new trace and split
from the script that dispatched it. asyncio tasks copy context automatically;
thread pools do not. This is the documented OpenTelemetry failure mode, and
OTel's threading instrumentation fixes it the same way.

patch_threadpool() wraps ThreadPoolExecutor.submit (which map() also uses) so
each task runs in a copy of the submitter's context. The submitter's flow is
started first, so every worker joins one trace rather than minting its own.

Known limitation: the copy is one-way. Reads made inside a worker do not flow
back to the submitter, so a write in the main thread after parallel reads is
not parented to them. Pinned as an xfail in tests/test_threads.py.
"""

import contextvars
from concurrent.futures import ThreadPoolExecutor

from dcp.context import ensure_trace

_patched = False


def patch_threadpool() -> None:
    """Make ThreadPoolExecutor tasks inherit the submitter's DCP context."""
    global _patched
    if _patched:
        return

    original_submit = ThreadPoolExecutor.submit

    def submit(self, fn, /, *args, **kwargs):
        ensure_trace()  # start the flow here, so all workers share it
        ctx = contextvars.copy_context()
        return original_submit(self, ctx.run, fn, *args, **kwargs)

    ThreadPoolExecutor.submit = submit
    _patched = True
