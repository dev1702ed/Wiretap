"""DCP events -> OpenLineage RunEvents. P4.

Mapping (rationale: docs/decisions/openlineage-mapping.md):

- One OpenLineage run per (trace_id, job.host, job.pid, job.name): one
  process's share of one trace. A DCP trace spans processes (a producer and
  its consumer share one), but an OpenLineage run belongs to one job.
- runId = uuid5(DCP_RUN_NAMESPACE, "|".join(run key)), so re-exporting the
  same events yields the same runs.
- Job namespace "dcp://{host}", job name = DCP job name: one script on two
  hosts is two jobs.
- inputs / outputs: the run's read / write datasets, unique and sorted.
  Dataset namespace and name are copied verbatim.
- A START event at the run's earliest ts and a COMPLETE event at its latest.
  DCP observes no process exit, so COMPLETE means "end of the observed
  window", not "the process finished".
- The COMPLETE event carries a `dcp` run facet with every DCP event of the
  run, so a DCP-aware consumer can recover the attested edges that
  OpenLineage's core model (inputs and outputs per run) cannot express.

The output depends only on the set of input events, never their order.
"""

import json
import uuid
from datetime import datetime, timezone

from dcp_openlineage import DCP_FACET_SCHEMA_URL, PRODUCER_URI, RUN_EVENT_SCHEMA_URL

# Fixed for good: changing it changes every runId the bridge has ever emitted.
# It is uuid5(NAMESPACE_URL, "https://github.com/dev1702ed/Wiretap/bridges/openlineage/run").
DCP_RUN_NAMESPACE = uuid.UUID("0c8af99c-3a1d-5111-8bf3-3ed587595f51")

UNKNOWN_HOST = "unknown-host"


def to_openlineage(events) -> list[dict]:
    """Translate DCP events into OpenLineage RunEvents, START then COMPLETE per run.

    Runs are ordered by start time, then job, then runId, so the same set of
    events always yields the same list. Identical duplicate events count once.
    """
    runs: dict[str, list[dict]] = {}
    for event in _distinct(events):
        runs.setdefault(run_id(event), []).append(event)

    translated = [_run_events(rid, members) for rid, members in runs.items()]
    translated.sort(key=lambda pair: pair[0])
    return [ol_event for _, run_events in translated for ol_event in run_events]


def run_key(event: dict) -> tuple[str, str, str, str]:
    job = event["job"]
    return (event["trace_id"], job.get("host", ""), str(job.get("pid", "")), job["name"])


def run_id(event: dict) -> str:
    return str(uuid.uuid5(DCP_RUN_NAMESPACE, "|".join(run_key(event))))


def job_namespace(job: dict) -> str:
    return f"dcp://{job.get('host') or UNKNOWN_HOST}"


def _run_events(rid: str, members: list[dict]) -> tuple[tuple, list[dict]]:
    times = sorted(_parse_ts(event["ts"]) for event in members)
    start, end = times[0], times[-1]
    job = members[0]["job"]
    ol_job = {"namespace": job_namespace(job), "name": job["name"]}
    inputs = _datasets(members, "read")
    outputs = _datasets(members, "write")

    def run_event(event_type: str, when: datetime, facets: dict | None) -> dict:
        run: dict = {"runId": rid}
        if facets:
            run["facets"] = facets
        return {
            "eventType": event_type,
            "eventTime": when.isoformat(),
            "producer": PRODUCER_URI,
            "schemaURL": RUN_EVENT_SCHEMA_URL,
            "run": run,
            "job": dict(ol_job),
            "inputs": [dict(d) for d in inputs],
            "outputs": [dict(d) for d in outputs],
        }

    facet = _dcp_facet(members)
    sort_key = (start, ol_job["namespace"], ol_job["name"], rid)
    return sort_key, [run_event("START", start, None), run_event("COMPLETE", end, {"dcp": facet})]


def _dcp_facet(members: list[dict]) -> dict:
    """Everything needed to rebuild the run's DCP events exactly."""
    first = members[0]
    entries = []
    for event in members:
        entry = {
            "edge_id": event["edge_id"],
            "op": event["op"],
            "dataset": {
                "namespace": event["dataset"]["namespace"],
                "name": event["dataset"]["name"],
            },
            "parent": list(event.get("parent", [])),
            "ts": event["ts"],
        }
        if "columns" in event:
            entry["columns"] = list(event["columns"])
        entries.append(entry)
    entries.sort(key=lambda e: (e["edge_id"], _canonical(e)))
    return {
        "_producer": PRODUCER_URI,
        "_schemaURL": DCP_FACET_SCHEMA_URL,
        "dcp_version": first["dcp_version"],
        "trace_id": first["trace_id"],
        "job": dict(first["job"]),
        "events": entries,
    }


def _datasets(members: list[dict], op: str) -> list[dict]:
    keys = {
        (event["dataset"]["namespace"], event["dataset"]["name"])
        for event in members
        if event["op"] == op
    }
    return [{"namespace": ns, "name": name} for ns, name in sorted(keys)]


def _parse_ts(ts: str) -> datetime:
    """ISO 8601 -> aware UTC datetime. A trailing Z is accepted on Python 3.10;
    a timestamp without an offset is taken as UTC."""
    try:
        parsed = datetime.fromisoformat(ts[:-1] + "+00:00" if ts.endswith("Z") else ts)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"DCP event has an unparseable ts: {ts!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _distinct(events) -> list[dict]:
    """Identical duplicates once, in a canonical order."""
    by_canonical = {_canonical(event): event for event in events}
    return [by_canonical[key] for key in sorted(by_canonical)]
