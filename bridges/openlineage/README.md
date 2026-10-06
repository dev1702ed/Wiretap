# OpenLineage bridge (P4)

**DCP feeds your existing catalog. It does not replace it.** This package translates
recorded DCP events into OpenLineage RunEvents, so DCP's lineage lands in Marquez,
DataHub or any other OpenLineage consumer.

It is a **batch** bridge over recorded events, not a live sink. Record with the file
sink, then translate (from the repository root; the same commands run in PowerShell):

```bash
pip install -e ./bridges/openlineage
# in the instrumented script:  dcp.init(emit="file://dcp_events.jsonl")
python -m dcp_openlineage --events dcp_events.jsonl --out openlineage.jsonl
python -m dcp_openlineage --events dcp_events.jsonl --post http://localhost:5000
python -m dcp_openlineage --events dcp_events.jsonl --run-scope process --out openlineage.jsonl
```

`--db PATH` reads the DCP backend's SQLite event log instead of (or as well as) a
JSONL file; it needs the backend installed. `--post` sends each event to
`URL/api/v1/lineage`, retries network errors and 5xx responses with backoff, and
exits non-zero if any event cannot be delivered. The bridge has no runtime
dependencies.

## Mapping

One OpenLineage **run** per process per trace: (`trace_id`, `job.host`, `job.pid`,
`job.name`), with a deterministic `runId`. Job namespace is `dcp://{host}`, job name is
the DCP job name, and dataset namespace and name are copied verbatim. Each run is a
`START` at its first DCP event and a `COMPLETE` at its last; `COMPLETE` means the end
of the observed window, not that the process exited.

`--run-scope process` (P5.2) maps **one run per process** instead: (`job.host`,
`job.pid`, `job.name`), with every input and output of the process, as a real
OpenLineage integration reports it. Its `dcp` facet adds `trace_ids` and a `trace_id`
per event, because one process can join several traces. Two processes with the same
name and pid on one host (pid reuse) merge into one run in that scope. The default,
`trace-process`, is unchanged.

The earlier leaning here was "trace → run". It was rejected because a DCP trace spans
processes (a producer and its consumer share one), while an OpenLineage run belongs to
one job. Full rationale: [`docs/decisions/openlineage-mapping.md`](../../docs/decisions/openlineage-mapping.md).

## What survives translation

OpenLineage's core run model lists inputs and outputs per run. It cannot say which
input fed which output, or which upstream run fed which downstream run. The `COMPLETE`
event therefore carries a `dcp` run facet with every DCP event of the run and its
parents (schema: [`facets/DcpRunFacet.json`](facets/DcpRunFacet.json)), so a DCP-aware
reader can rebuild the attested graph exactly. What is lost without the facet is
measured in `benchmarks/ground_truth/score.py`; results are in
[`docs/results/P4.md`](../../docs/results/P4.md).

## Layout

| Path | What |
|---|---|
| `dcp_openlineage/translate.py` | `to_openlineage(events)` |
| `dcp_openlineage/reconstruct.py` | Read OpenLineage back: implied edges, provenance, DCP events from facets |
| `dcp_openlineage/transport.py` | POST to `/api/v1/lineage`, with retries |
| `dcp_openlineage/__main__.py` | The CLI |
| `schema/OpenLineage.json` | The official spec, vendored at release tag 1.53.0 (see `schema/README.md`) |
| `facets/DcpRunFacet.json` | The `dcp` run facet's schema |
