"""DCP's start-up hook for dcp-instrument. P5; post-import hooks since P5.1.

dcp-instrument puts this file's directory first on PYTHONPATH, so Python's
`site` module imports it at interpreter start-up, before any user import. It:

1. calls dcp.init() from DCP_EMIT, DCP_JOB_NAME, DCP_PROPAGATE_SQL and
   DCP_CAPTURE;
2. arranges for psycopg, confluent-kafka and ThreadPoolExecutor to be patched
   WHEN, and only when, the program imports them: a post-import hook on
   sys.meta_path runs each patch right after its module has executed, before
   the import statement that triggered it returns. So
   `from confluent_kafka import Producer` still binds the patched class, a
   library imported inside a function is still captured, and a program that
   never imports psycopg never loads psycopg (or sqlglot, which DCP itself
   imports only on its first classification);
3. runs the sitecustomize this one shadows, if there is one further along
   sys.path (Debian and Ubuntu ship one, for example).

Monitor-only: a DCP failure in steps 1-2, or in a patch when its library is
imported, is caught and logged at debug, and the program runs uninstrumented.
An error raised by the chained sitecustomize is left alone, so Python reports
it exactly as it would without DCP.

Keep this directory free of other modules: everything in it becomes
importable by top-level name in the instrumented program.
"""

import logging
import os
import sys

_log = logging.getLogger("dcp")
_HERE = os.path.dirname(os.path.realpath(__file__))

# Module -> the name of the dcp function that patches it, run once, right after
# the module executes. concurrent.futures.thread defines ThreadPoolExecutor.
HOOKS = {
    "psycopg": "patch_psycopg",
    "confluent_kafka": "patch_kafka",
    "concurrent.futures.thread": "patch_threadpool",
}


def _job_name() -> str | None:
    """DCP_JOB_NAME, else the script's basename (dcp.init's default).

    Under `python -m pkg.mod`, sys.argv[0] is still "-m" at start-up, so the
    module name is taken from sys.orig_argv instead.
    """
    name = os.environ.get("DCP_JOB_NAME")
    if name:
        return name
    if sys.argv[:1] == ["-m"]:
        orig = list(getattr(sys, "orig_argv", []))
        if "-m" in orig and orig.index("-m") + 1 < len(orig):
            return orig[orig.index("-m") + 1]
    return None


def capture_off(value: str | None) -> bool:
    """DCP_CAPTURE=off (or 0, false, no; any case) is the kill switch."""
    return (value or "").strip().lower() in ("off", "0", "false", "no")


def _patch(module: str) -> None:
    """Run the patch for `module`, now that it has been imported. Monitor-only."""
    try:
        import dcp

        getattr(dcp, HOOKS[module])()
    except Exception:  # noqa: BLE001 — monitor-only: one library must not block the others
        _log.debug("dcp-instrument could not patch %s", module, exc_info=True)


class _PatchingLoader:
    """Wraps a module's real loader: execute the module, then patch it.

    Every other attribute is the real loader's, and the module's __loader__ and
    __spec__.loader are put back once it has executed, so nothing downstream
    (importlib.resources, pkgutil, reloads) ever sees this wrapper.
    """

    def __init__(self, loader, name: str):
        self._loader = loader
        self._name = name

    def __getattr__(self, attr):
        return getattr(self._loader, attr)

    def create_module(self, spec):
        return self._loader.create_module(spec)

    def exec_module(self, module) -> None:
        if getattr(module, "__loader__", None) is self:
            module.__loader__ = self._loader
        spec = getattr(module, "__spec__", None)
        if spec is not None and spec.loader is self:
            spec.loader = self._loader
        self._loader.exec_module(module)
        _patch(self._name)


class PostImportFinder:
    """A sys.meta_path entry that hooks the modules in HOOKS, once each.

    It finds nothing itself: it asks the rest of sys.meta_path for the spec
    (guarding against finding itself) and wraps that spec's loader.
    """

    def __init__(self, names):
        self._pending = set(names)
        self._finding: set[str] = set()

    def find_spec(self, fullname, path=None, target=None):
        if fullname not in self._pending or fullname in self._finding:
            return None
        self._finding.add(fullname)
        try:
            import importlib.util

            spec = importlib.util.find_spec(fullname)
        finally:
            self._finding.discard(fullname)
        if spec is None or spec.loader is None or not hasattr(spec.loader, "exec_module"):
            return None
        self._pending.discard(fullname)  # one-shot: a re-import is not re-patched
        spec.loader = _PatchingLoader(spec.loader, fullname)
        return spec

    def invalidate_caches(self) -> None:
        return None


def install_hooks() -> None:
    """Patch what is already imported; hook the rest."""
    waiting = []
    for name in HOOKS:
        if name in sys.modules:
            _patch(name)
        else:
            waiting.append(name)
    if waiting:
        sys.meta_path.insert(0, PostImportFinder(waiting))


def _start_dcp() -> None:
    import dcp

    dcp.init(
        emit=os.environ.get("DCP_EMIT") or "console",
        job_name=_job_name(),
        propagate_sql=os.environ.get("DCP_PROPAGATE_SQL") == "1",
        capture=not capture_off(os.environ.get("DCP_CAPTURE")),
    )
    install_hooks()


def _chain() -> None:
    """Run the next sitecustomize on sys.path, the one this file shadows."""
    import importlib.machinery
    import importlib.util

    rest = [p for p in sys.path if os.path.realpath(p or os.curdir) != _HERE]
    spec = importlib.machinery.PathFinder.find_spec("sitecustomize", rest)
    if spec is None or spec.loader is None:
        return
    if spec.origin and os.path.dirname(os.path.realpath(spec.origin)) == _HERE:
        return
    module = importlib.util.module_from_spec(spec)
    sys.modules["sitecustomize"] = module  # later `import sitecustomize` sees theirs
    spec.loader.exec_module(module)


try:
    _start_dcp()
except Exception:  # noqa: BLE001 — monitor-only: the program must run regardless
    _log.debug("dcp-instrument could not start DCP; running uninstrumented", exc_info=True)

_chain()
