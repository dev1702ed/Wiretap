"""The wire contract between the SDK's HTTPEmitter and POST /events.

Needs the SDK as well as the backend; CI installs both.
"""

import socket
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

from app.main import create_app

pytest.importorskip("dcp")

from dcp.config import JobIdentity
from dcp.emitters.http import CONTENT_TYPE, HTTPEmitter, encode_batch
from dcp.envelope import Dataset, DCPEvent, new_id

JOB = JobIdentity("nightly_enrich.py", "analyst-vm-04", 48213)
ORDERS = Dataset(namespace="postgres://localhost:5432", name="dcp.public.orders")
TOPIC = Dataset(namespace="kafka://localhost:9092", name="enriched_orders")


def sdk_events() -> list[DCPEvent]:
    """A read and the produce it feeds, built by the SDK's own envelope code."""
    trace = new_id()
    read = DCPEvent(trace_id=trace, edge_id=new_id(), op="read", dataset=ORDERS, job=JOB)
    write = DCPEvent(
        trace_id=trace,
        edge_id=new_id(),
        op="write",
        dataset=TOPIC,
        job=JOB,
        parent=[read.edge_id],
        columns=["order_id", "order_total"],
    )
    return [read, write]


def test_emitter_body_is_accepted(tmp_path):
    events = sdk_events()
    body = encode_batch([event.to_dict() for event in events])
    with TestClient(create_app(tmp_path / "events.db")) as client:
        response = client.post("/events", content=body, headers={"Content-Type": CONTENT_TYPE})
        assert response.status_code == 200
        assert response.json() == {"accepted": 2}
        edges = client.get("/graph").json()["dataset_edges"]
    assert edges == [
        {
            "from": {"namespace": ORDERS.namespace, "name": ORDERS.name},
            "to": {"namespace": TOPIC.namespace, "name": TOPIC.name},
            "job": JOB.name,
        }
    ]


def test_emitter_delivers_to_a_running_backend(tmp_path):
    """End to end over a real socket: HTTPEmitter -> uvicorn -> the event log."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(tmp_path / "events.db"), log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        for _ in range(200):
            if server.started:
                break
            time.sleep(0.05)
        assert server.started

        emitter = HTTPEmitter(f"http://127.0.0.1:{port}", max_retries=0)
        events = sdk_events()
        for event in events:
            emitter.emit(event)
        emitter.close(timeout=10)
        assert emitter.dropped == 0

        with TestClient(create_app(tmp_path / "events.db")) as client:
            stored = client.get("/graph").json()
        assert stored["event_count"] == 2
        assert len(stored["dataset_edges"]) == 1
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
