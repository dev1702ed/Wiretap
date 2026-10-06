"""FastAPI app. P3.

Endpoints:
    POST /events                                  ingest one event or a JSON array
    GET  /upstream?namespace=&name=&level=run     provenance — what fed this dataset?
    GET  /downstream?namespace=&name=             blast radius — what does it feed?
    GET  /graph                                   whole graph, for the viewer and benchmarks
    GET  /health

Dataset keys contain `://` and `/`, so they are query parameters rather than
path segments (the roadmap's `/downstream/{dataset}` form would need them
escaped). On startup the graph is rebuilt by replaying the event log.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Body, FastAPI, HTTPException, Request

from app.graph import Dataset
from app.identity import resolve
from app.ingest import Ingestor, InvalidEvents
from app.store import EventStore

router = APIRouter()


def create_app(db_path: str | os.PathLike | None = None) -> FastAPI:
    """Build the app. `db_path` overrides $DCP_DB_PATH; tests pass a tmp path."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = EventStore(db_path)
        app.state.ingestor = Ingestor(store)  # replays the log into the graph
        try:
            yield
        finally:
            store.close()

    app = FastAPI(title="DCP Backend", version="0.1.0", lifespan=lifespan)
    app.include_router(router)
    return app


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.post("/events")
def post_events(request: Request, payload: Annotated[dict[str, Any] | list[Any], Body()]) -> dict:
    """Ingest one event or a JSON array of events, atomically."""
    try:
        accepted = _ingestor(request).ingest(payload)
    except InvalidEvents as exc:
        raise HTTPException(status_code=422, detail=exc.errors) from exc
    return {"accepted": accepted}


@router.get("/upstream")
def get_upstream(
    request: Request,
    namespace: str,
    name: str,
    level: Literal["run", "dataset"] = "run",
) -> dict:
    """Run-level provenance by default; `level=dataset` for the dataset-level baseline."""
    ingestor = _ingestor(request)
    with ingestor.lock:
        dataset = _known(ingestor, namespace, name)
        graph = ingestor.graph
        found = graph.upstream(dataset) if level == "run" else graph.dataset_upstream(dataset)
    return {"dataset": _ds(dataset), "level": level, "upstream": _ds_list(found)}


@router.get("/downstream")
def get_downstream(request: Request, namespace: str, name: str) -> dict:
    """Blast radius: dataset-level descendants."""
    ingestor = _ingestor(request)
    with ingestor.lock:
        dataset = _known(ingestor, namespace, name)
        found = ingestor.graph.downstream(dataset)
    return {"dataset": _ds(dataset), "downstream": _ds_list(found)}


@router.get("/graph")
def get_graph(request: Request) -> dict:
    ingestor = _ingestor(request)
    with ingestor.lock:
        graph = ingestor.graph
        datasets = graph.datasets()
        dataset_edges = graph.dataset_edges()
        run_edges = graph.run_edges()
        event_count = graph.event_count()
        dangling = len(graph.dangling_parents())
        conflicting = len(graph.conflicting_edge_ids())
    return {
        "datasets": _ds_list(datasets),
        "dataset_edges": [
            {"from": _ds(src), "to": _ds(dst), "job": job}
            for src, dst, job in sorted(dataset_edges)
        ],
        "run_edges": [
            {"from_job": from_job, "to_job": to_job, "via": _ds(via)}
            for from_job, to_job, via in sorted(run_edges)
        ],
        "event_count": event_count,
        "dangling_parent_count": dangling,
        "conflicting_edge_id_count": conflicting,
    }


def _ingestor(request: Request) -> Ingestor:
    return request.app.state.ingestor


def _known(ingestor: Ingestor, namespace: str, name: str) -> Dataset:
    dataset = resolve(namespace, name)
    if dataset not in ingestor.graph.datasets():
        raise HTTPException(status_code=404, detail=f"unknown dataset {namespace} {name}")
    return dataset


def _ds(dataset: Dataset) -> dict:
    return {"namespace": dataset[0], "name": dataset[1]}


def _ds_list(datasets: set[Dataset]) -> list[dict]:
    return [_ds(dataset) for dataset in sorted(datasets)]


app = create_app()
