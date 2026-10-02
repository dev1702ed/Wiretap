"""The lineage graph: semantics, order-independence, cycles, dangling parents."""

import itertools

import pytest
from app.graph import LineageGraph, build

PG = "postgres://localhost:5432"
KAFKA = "kafka://localhost:9092"
ORDERS = (PG, "dcp.public.orders")
REFUNDS = (PG, "dcp.public.refunds")
CUSTOMERS = (PG, "dcp.public.customers")
TOPIC = (KAFKA, "enriched_orders")
REVENUE = (PG, "dcp.public.daily_revenue")


@pytest.fixture
def fan_in(ev):
    """topic_fan_in by hand: two producers share a topic, and the consumer
    processes only enrich_orders.py's record. Plus one read nothing uses."""
    return [
        ev("r-orders", "read", ORDERS, "enrich_orders.py"),
        ev("w-a", "write", TOPIC, "enrich_orders.py", ["r-orders"]),
        ev("r-refunds", "read", REFUNDS, "enrich_refunds.py"),
        ev("w-b", "write", TOPIC, "enrich_refunds.py", ["r-refunds"]),
        ev("r-topic", "read", TOPIC, "revenue_loader.py", ["w-a"]),
        ev("w-revenue", "write", REVENUE, "revenue_loader.py", ["r-topic"]),
        ev("r-customers", "read", CUSTOMERS, "audit.py"),
    ]


def everything(g: LineageGraph) -> dict:
    """Every answer the graph gives, for comparing two graphs."""
    return {
        "snapshot": g.snapshot(),
        "dangling": g.dangling_parents(),
        **{
            f"{query}:{ds}": getattr(g, query)(ds)
            for ds in sorted(g.datasets())
            for query in ("upstream", "dataset_upstream", "downstream")
        },
    }


# --- The semantics table ---------------------------------------------------


def test_datasets_are_every_dataset_in_any_event(fan_in):
    assert build(fan_in).datasets() == {ORDERS, REFUNDS, CUSTOMERS, TOPIC, REVENUE}


def test_dataset_edges_link_a_read_to_the_write_it_parents(fan_in):
    assert build(fan_in).dataset_edges() == {
        (ORDERS, TOPIC, "enrich_orders.py"),
        (REFUNDS, TOPIC, "enrich_refunds.py"),
        (TOPIC, REVENUE, "revenue_loader.py"),
    }


def test_run_edges_link_a_write_to_the_read_it_parents(fan_in):
    assert build(fan_in).run_edges() == {
        ("enrich_orders.py", "revenue_loader.py", TOPIC)
    }


def test_upstream_is_run_level_provenance(fan_in):
    g = build(fan_in)
    assert g.upstream(REVENUE) == {TOPIC, ORDERS}
    assert g.upstream(TOPIC) == {ORDERS, REFUNDS}  # every write to the topic
    assert g.upstream(ORDERS) == set()


def test_dataset_upstream_is_the_dataset_level_baseline(fan_in):
    """Over-approximates: refunds reaches daily_revenue through the shared topic."""
    g = build(fan_in)
    assert g.dataset_upstream(REVENUE) == {TOPIC, ORDERS, REFUNDS}
    assert g.upstream(REVENUE) < g.dataset_upstream(REVENUE)


def test_downstream_is_dataset_level_blast_radius(fan_in):
    """Deliberately dataset-level: impact analysis wants recall."""
    g = build(fan_in)
    assert g.downstream(REFUNDS) == {TOPIC, REVENUE}
    assert g.downstream(REVENUE) == set()
    assert g.downstream(CUSTOMERS) == set()


def test_unknown_dataset_answers_empty(fan_in):
    g = build(fan_in)
    unknown = (PG, "dcp.public.nope")
    assert (
        g.upstream(unknown)
        == g.dataset_upstream(unknown)
        == g.downstream(unknown)
        == set()
    )


def test_upstream_never_falls_back_to_dataset_level(ev):
    """Store-mediated links are not inferred: warehouse.py read `staging`
    after etl.py wrote it, but rows carry no metadata, so nothing attests that
    it read etl.py's rows. Run-level provenance stops at the table."""
    source, staging, report = (
        (PG, "dcp.public.source"),
        (PG, "dcp.public.staging"),
        (PG, "r"),
    )
    g = build(
        [
            ev("r-src", "read", source, "etl.py"),
            ev("w-stg", "write", staging, "etl.py", ["r-src"]),
            ev("r-stg", "read", staging, "warehouse.py"),  # Postgres reads: parent []
            ev("w-rep", "write", report, "warehouse.py", ["r-stg"]),
        ]
    )
    assert g.upstream(report) == {staging}
    assert g.dataset_upstream(report) == {staging, source}
    assert g.run_edges() == set()


def test_write_with_no_parents_has_no_upstream(ev):
    g = build([ev("r", "read", ORDERS), ev("w", "write", REVENUE)])
    assert g.upstream(REVENUE) == set()
    assert g.dataset_edges() == set()


# --- Order independence ----------------------------------------------------


def test_every_permutation_builds_the_same_graph(fan_in):
    """HTTP emitters race: a child can arrive before its parent."""
    events = fan_in[:6]
    reference = everything(build(events))
    for order in itertools.permutations(events):
        assert everything(build(list(order))) == reference


def test_child_before_parent_links_when_the_parent_arrives(ev):
    g = LineageGraph()
    g.add(ev("w", "write", TOPIC, "enrich.py", ["r"]))
    assert g.dangling_parents() == {"r"}
    assert g.dataset_edges() == set()
    g.add(ev("r", "read", ORDERS, "enrich.py"))
    assert g.dangling_parents() == set()
    assert g.dataset_edges() == {(ORDERS, TOPIC, "enrich.py")}
    assert g.upstream(TOPIC) == {ORDERS}


def test_identical_duplicate_is_a_no_op(fan_in):
    """At-least-once delivery: a retried POST may land twice."""
    g = build(fan_in)
    for event in fan_in:
        g.add(dict(event))
    assert g == build(fan_in)
    assert g.event_count() == len(fan_in)


def test_conflicting_events_with_one_edge_id_are_order_independent(ev):
    """Two different events claiming one edge_id should never happen. If it
    does, both are kept and a parent reference resolves to each, whatever the
    arrival order, rather than whichever came first."""
    events = [
        ev("r1", "read", ORDERS, "a.py"),
        ev("r2", "read", REFUNDS, "a.py"),
        ev("w", "write", TOPIC, "a.py", ["r1"]),
        ev("w", "write", REVENUE, "b.py", ["r2"]),
        ev("c", "read", TOPIC, "c.py", ["w"]),
    ]
    reference = everything(build(events))
    for order in itertools.permutations(events):
        assert everything(build(list(order))) == reference
    assert reference["snapshot"]["dataset_edges"] == {
        (ORDERS, TOPIC, "a.py"),
        (REFUNDS, TOPIC, "a.py"),
        (ORDERS, REVENUE, "b.py"),
        (REFUNDS, REVENUE, "b.py"),
    }


def test_build_is_a_fold_over_add(fan_in):
    g = LineageGraph()
    for event in fan_in:
        g.add(event)
    assert g == build(fan_in)


# --- Cycles ----------------------------------------------------------------


def test_self_loop_terminates(ev):
    """UPDATE t SET ... WHERE id IN (SELECT id FROM t): t feeds itself."""
    t = (PG, "dcp.public.t")
    g = build([ev("r", "read", t, "fix.py"), ev("w", "write", t, "fix.py", ["r"])])
    assert g.dataset_edges() == {(t, t, "fix.py")}
    assert g.upstream(t) == set()
    assert g.dataset_upstream(t) == set()
    assert g.downstream(t) == set()


def test_self_loop_inside_a_chain(ev):
    s, t, u = (PG, "s"), (PG, "t"), (PG, "u")
    g = build(
        [
            ev("r-s", "read", s),
            ev("w-t1", "write", t, parent=["r-s"]),
            ev("r-t1", "read", t),
            ev("w-t2", "write", t, parent=["r-t1"]),
            ev("r-t2", "read", t),
            ev("w-u", "write", u, parent=["r-t2"]),
        ]
    )
    assert g.dataset_upstream(u) == {t, s}
    assert g.downstream(s) == {t, u}
    assert g.downstream(t) == {u}
    assert g.upstream(t) == {s}
    assert g.upstream(u) == {t}


def test_cycle_between_datasets_terminates(ev):
    a, b = (PG, "a"), (PG, "b")
    g = build(
        [
            ev("r-a", "read", a),
            ev("w-b", "write", b, parent=["r-a"]),
            ev("r-b", "read", b),
            ev("w-a", "write", a, parent=["r-b"]),
        ]
    )
    assert g.dataset_upstream(a) == g.downstream(a) == {b}
    assert g.dataset_upstream(b) == g.downstream(b) == {a}


def test_cycle_in_parent_links_terminates(ev):
    """Malformed input: two events each naming the other as parent."""
    g = build(
        [
            ev("x", "read", ORDERS, parent=["y"]),
            ev("y", "write", TOPIC, parent=["x"]),
        ]
    )
    assert g.upstream(TOPIC) == {ORDERS}
    assert g.dataset_edges() == {(ORDERS, TOPIC, "job.py")}
    assert g.run_edges() == {("job.py", "job.py", ORDERS)}


def test_event_naming_itself_as_parent_terminates(ev):
    g = build([ev("x", "write", TOPIC, parent=["x"])])
    assert g.upstream(TOPIC) == set()
    assert g.dangling_parents() == set()


# --- Dangling parents ------------------------------------------------------


def test_dangling_parents_are_tolerated_and_reported(ev):
    g = build(
        [
            ev("r", "read", TOPIC, "consumer.py", ["never-seen"]),
            ev("w", "write", REVENUE, "consumer.py", ["r", "also-never-seen"]),
        ]
    )
    assert g.dangling_parents() == {"never-seen", "also-never-seen"}
    assert g.upstream(REVENUE) == {TOPIC}
    assert g.dataset_edges() == {(TOPIC, REVENUE, "consumer.py")}
    assert g.run_edges() == set()


# --- Identity --------------------------------------------------------------


def test_datasets_are_keyed_by_resolved_identity(ev):
    g = build(
        [
            ev("r1", "read", ("  POSTGRES://LocalHost:5432 ", "dcp.public.orders")),
            ev("r2", "read", (PG, "dcp.public.orders")),
            ev("r3", "read", ("postgres://127.0.0.1:5432", "dcp.public.orders")),
            ev("r4", "read", (PG, "dcp.public.Orders")),
        ]
    )
    assert g.datasets() == {
        ORDERS,
        ("postgres://127.0.0.1:5432", "dcp.public.orders"),
        (PG, "dcp.public.Orders"),
    }
    assert g.downstream(("postgres://LOCALHOST:5432", "dcp.public.orders")) == set()


def test_conflicting_edge_ids_are_reported(ev):
    """Two different events claiming one edge_id: an integrity signal."""
    g = build(
        [
            ev("w", "write", TOPIC, "a.py"),
            ev("w", "write", REVENUE, "b.py"),
            ev("r", "read", ORDERS),
        ]
    )
    assert g.conflicting_edge_ids() == {"w"}


def test_identical_duplicates_are_not_conflicts(fan_in):
    g = build(fan_in + [dict(event) for event in fan_in])
    assert g.conflicting_edge_ids() == set()
