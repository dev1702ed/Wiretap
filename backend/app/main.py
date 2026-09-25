"""FastAPI app. P3.

Endpoints:
    POST /events              ingest a DCP event (schema-validated)
    GET  /downstream/{ds}     blast radius — what does this dataset feed?
    GET  /upstream/{ds}       provenance — what fed this dataset?
    GET  /graph               whole graph, for the viewer and the benchmarks
"""

from fastapi import FastAPI

app = FastAPI(title="DCP Backend", version="0.1.0.dev0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
