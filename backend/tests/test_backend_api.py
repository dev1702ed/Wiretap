"""Every endpoint, through FastAPI's TestClient against a tmp_path event log."""

import pytest
from app.main import create_app
from fastapi.testclient import TestClient

PG = "postgres://localhost:5432"
KAFKA = "kafka://localhost:9092"
ORDERS = (PG, "dcp.public.orders")
REFUNDS = (PG, "dcp.public.refunds")
TOPIC = (KAFKA, "enriched_orders")
REVENUE = (PG, "dcp.public.daily_revenue")


def ds(dataset):
    return {"namespace": dataset[0], "name": dataset[1]}


def query(dataset, **extra):
    return {"namespace": dataset[0], "name": dataset[1], **extra}


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "events.db"


@pytest.fixture
def client(db_path):
    with TestClient(create_app(db_path)) as test_client:  # `with` runs the lifespan
        yield test_client


@pytest.fixture
def fan_in(ev):
    return [
        ev("r-orders", "read", ORDERS, "enrich_orders.py"),
        ev("w-a", "write", TOPIC, "enrich_orders.py", ["r-orders"]),
        ev("r-refunds", "read", REFUNDS, "enrich_refunds.py"),
        ev("w-b", "write", TOPIC, "enrich_refunds.py", ["r-refunds"]),
        ev("r-topic", "read", TOPIC, "revenue_loader.py", ["w-a"]),
        ev("w-revenue", "write", REVENUE, "revenue_loader.py", ["r-topic", "gone"]),
    ]


@pytest.fixture
def loaded(client, fan_in):
    assert client.post("/events", json=fan_in).status_code == 200
    return client


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_post_one_event(client, ev):
    response = client.post("/events", json=ev("r", "read", ORDERS))
    assert response.status_code == 200
    assert response.json() == {"accepted": 1}


def test_post_an_array(client, fan_in):
    response = client.post("/events", json=fan_in)
    assert response.status_code == 200
    assert response.json() == {"accepted": len(fan_in)}
    assert client.get("/graph").json()["event_count"] == len(fan_in)


def test_invalid_batch_is_422_and_stores_nothing(client, ev, db_path):
    bad = ev("w", "write", REVENUE)
    del bad["job"]
    response = client.post("/events", json=[ev("r", "read", ORDERS), bad])
    assert response.status_code == 422
    assert [error["index"] for error in response.json()["detail"]] == [1]
    assert client.get("/graph").json()["event_count"] == 0
    with TestClient(create_app(db_path)) as restarted:
        assert restarted.get("/graph").json()["event_count"] == 0


@pytest.mark.parametrize("body", [b"{not json", b'"a string"', b"42"])
def test_malformed_body_is_422(client, body):
    response = client.post(
        "/events", content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert client.get("/graph").json()["event_count"] == 0


def test_upstream_defaults_to_run_level(loaded):
    response = loaded.get("/upstream", params=query(REVENUE))
    assert response.status_code == 200
    assert response.json() == {
        "dataset": ds(REVENUE),
        "level": "run",
        "upstream": [ds(TOPIC), ds(ORDERS)],
    }
    assert (
        loaded.get("/upstream", params=query(REVENUE, level="run")).json()
        == response.json()
    )


def test_upstream_dataset_level_is_the_baseline(loaded):
    response = loaded.get("/upstream", params=query(REVENUE, level="dataset"))
    assert response.status_code == 200
    assert response.json() == {
        "dataset": ds(REVENUE),
        "level": "dataset",
        "upstream": [ds(TOPIC), ds(ORDERS), ds(REFUNDS)],
    }


def test_downstream(loaded):
    response = loaded.get("/downstream", params=query(REFUNDS))
    assert response.status_code == 200
    assert response.json() == {
        "dataset": ds(REFUNDS),
        "downstream": [ds(TOPIC), ds(REVENUE)],
    }


def test_query_resolves_identity(loaded):
    response = loaded.get(
        "/downstream", params=query(("POSTGRES://LocalHost:5432", ORDERS[1]))
    )
    assert response.status_code == 200
    assert response.json()["dataset"] == ds(ORDERS)


@pytest.mark.parametrize("path", ["/upstream", "/downstream"])
def test_unknown_dataset_is_404(loaded, path):
    response = loaded.get(path, params=query((PG, "dcp.public.nope")))
    assert response.status_code == 404


@pytest.mark.parametrize(
    "params",
    [
        {"name": ORDERS[1]},
        {"namespace": ORDERS[0]},
        query(ORDERS, level="table"),
    ],
)
def test_bad_query_is_422(loaded, params):
    assert loaded.get("/upstream", params=params).status_code == 422


def test_graph(loaded):
    assert loaded.get("/graph").json() == {
        "datasets": [ds(TOPIC), ds(REVENUE), ds(ORDERS), ds(REFUNDS)],
        "dataset_edges": [
            {"from": ds(TOPIC), "to": ds(REVENUE), "job": "revenue_loader.py"},
            {"from": ds(ORDERS), "to": ds(TOPIC), "job": "enrich_orders.py"},
            {"from": ds(REFUNDS), "to": ds(TOPIC), "job": "enrich_refunds.py"},
        ],
        "run_edges": [
            {
                "from_job": "enrich_orders.py",
                "to_job": "revenue_loader.py",
                "via": ds(TOPIC),
            },
        ],
        "event_count": 6,
        "dangling_parent_count": 1,
    }


def test_restart_rebuilds_the_graph_from_the_log(loaded, db_path):
    before = loaded.get("/graph").json()
    upstream = loaded.get("/upstream", params=query(REVENUE)).json()
    with TestClient(create_app(db_path)) as restarted:
        assert restarted.get("/graph").json() == before
        assert restarted.get("/upstream", params=query(REVENUE)).json() == upstream
