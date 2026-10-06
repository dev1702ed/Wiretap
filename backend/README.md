# dcp-backend — the DCP lineage backend

Stores every DCP event in an append-only SQLite log, rebuilds the lineage graph from it
exactly, and answers run-level provenance, dataset-level lineage and blast-radius
queries over an HTTP API (FastAPI).

Not on PyPI; install from a clone of the repository:

```bash
pip install -e ./backend
uvicorn app.main:app
```

Documentation, the event format and the measured results are in the project
repository: https://github.com/dev1702ed/Wiretap. Licensed under Apache 2.0.
