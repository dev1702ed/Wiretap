"""Every emitted event must validate against spec/envelope.schema.json.

This test is the mechanism that keeps the spec honest. A spec that drifts from
the implementation is worthless as a durable artifact — and the spec is the most
durable thing in this repo.

P0: this file exists and fails. That is intended.
"""

import json
import pathlib

SCHEMA_PATH = pathlib.Path(__file__).parents[2] / "spec" / "envelope.schema.json"


def test_schema_file_is_valid_json():
    json.loads(SCHEMA_PATH.read_text())


def test_emitted_event_matches_schema():
    import jsonschema

    from dcp.config import JobIdentity
    from dcp.envelope import Dataset, DCPEvent, new_id

    schema = json.loads(SCHEMA_PATH.read_text())
    job = JobIdentity(name="test_job.py", host="test-host", pid=123)
    event = DCPEvent(
        trace_id=new_id(),
        edge_id=new_id(),
        op="read",
        dataset=Dataset(namespace="postgres://localhost:5432", name="sales.public.orders"),
        job=job,
        columns=["order_id", "order_total"],
    )
    jsonschema.validate(event.to_dict(), schema)
