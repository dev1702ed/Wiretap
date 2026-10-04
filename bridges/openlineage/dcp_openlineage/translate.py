"""DCP events -> OpenLineage RunEvents. P4; the run-scope option is P5.2.

Mapping (rationale: docs/decisions/openlineage-mapping.md):

- The run scope (`run_scope`) says which events form one OpenLineage run:
  - "trace-process", the default: one run per (trace_id, job.host, job.pid,
    job.name), one process's share of one trace. A DCP trace spans processes
    (a producer and its consumer share one), but an OpenLineage run belongs to
    one job;
  - "process" (P5.2): one run per (job.host, job.pid, job.name), every event
    of one process, as a real OpenLineage integration reports it: one run with
    all of the process's inputs and outputs, however many traces it joined.
    Two processes with the same job name and pid on the same host (pid reuse)
    merge into one run: DCP events carry no process start time.
- runId = uuid5(DCP_RUN_NAMESPACE, "|".join(run key)), so re-exporting the
  same events yields the same runs. A "process" run key starts with
  "process", a "trace-process" key with a trace_id (a UUID), so the two
  scopes never produce the same runId.
- Job namespace "dcp://{host}", job name = DCP job name: one script on two
  hosts is two jobs.
- inputs / outputs: the run's read / write datasets, unique and sorted.
  Dataset namespace and name are copied verbatim.
- A START event at the run's earliest ts and a COMPLETE event at its latest.
  DCP observes no process exit, so COMPLETE means "end of the observed
  window", not "the process finished".
- The COMPLETE event carries a `dcp` run facet with every DCP event of the
  run, so a DCP-aware consumer can recover the attested edges that
  OpenLineage's core model (inputs and outputs per run) cannot express. A
  "process" run can span several traces: its facet adds `trace_ids` (sorted;
  `trace_id` stays the first of them) and each event's own `trace_id`.

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

TRACE_PROCESS = "trace-process"
PROCESS = "process"
RUN_SCOPES = (TRACE_PROCESS, PROCESS)
DEFAULT_RUN_SCOPE = TRACE_PROCESS


def to_openlineage(events, run_scope: str = DEFAULT_RUN_SCOPE) -> list[dict]:
    """Translate DCP events into OpenLineage RunEvents, START then COMPLETE per run.

    `run_scope` is "trace-process" (the default) or "process"; see the module
    docstring. Runs are ordered by start time, then job, then runId, so the
    same set of events always yields the same list. Identical duplicate
    events count once.
    """
    _check_scope(run_scope)
    runs: dict[str, list[dict]] = {}
    for event in _distinct(events):
        runs.setdefault(run_id(event, run_scope), []).append(event)

    translated = [_run_events(rid, members, run_scope) for rid, members in runs.items()]
    translated.sort(key=lambda pair: pair[0])
    return [ol_event for _, run_events in translated for ol_event in run_events]


def run_key(event: dict) -> tuple[str, str, str, str]:
    job = event["job"]
    return (event["trace_id"], job.get("host", ""), str(job.get("pid", "")), job["name"])


def process_key(event: dict) -> tuple[str, str, str, str]:
    """The "process" run key: (job.host, job.pid, job.name), after a fixed
    "process" prefix that no trace_id-led key can share."""
    job = event["job"]
    return (PROCESS, job.get("host", ""), str(job.get("pid", "")), job["name"])


def run_id(event: dict, run_scope: str = DEFAULT_RUN_SCOPE) -> str:
    _check_scope(run_scope)
    key = process_key(event) if run_scope == PROCESS else run_key(event)
    return str(uuid.uuid5(DCP_RUN_NAMESPACE, "|".join(key)))


def _check_scope(run_scope: str) -> None:
    if run_scope not in RUN_SCOPES:
        raise ValueError(f"unknown run scope {run_scope!r}; choose from {', '.join(RUN_SCOPES)}")


def job_namespace(job: dict) -> str:
    return f"dcp://{job.get('host') or UNKNOWN_HOST}"


def _run_events(rid: str, members: list[dict], run_scope: str) -> tuple[tuple, list[dict]]:
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

    facet = _dcp_facet(members, per_event_traces=run_scope == PROCESS)
    sort_key = (start, ol_job["namespace"], ol_job["name"], rid)
    return sort_key, [run_event("START", start, None), run_event("COMPLETE", end, {"dcp": facet})]


def _dcp_facet(members: list[dict], per_event_traces: bool = False) -> dict:
    """Everything needed to rebuild the run's DCP events exactly.

    With `per_event_traces` (the "process" scope, whose run can span traces),
    every entry carries its own trace_id, and the facet lists the run's traces
    in `trace_ids`, sorted, with `trace_id` the first of them."""
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
        if per_event_traces:
            entry["trace_id"] = event["trace_id"]
        entries.append(entry)
    entries.sort(key=lambda e: (e["edge_id"], _canonical(e)))
    facet = {
        "_producer": PRODUCER_URI,
        "_schemaURL": DCP_FACET_SCHEMA_URL,
        "dcp_version": first["dcp_version"],
        "trace_id": first["trace_id"],
        "job": dict(first["job"]),
        "events": entries,
    }
    if per_event_traces:
        traces = sorted({event["trace_id"] for event in members})
        facet["trace_id"] = traces[0]
        facet["trace_ids"] = traces
    return facet


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
