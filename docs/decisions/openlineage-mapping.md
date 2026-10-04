# Decision: how DCP events map to OpenLineage

Status: decided in P4; the run-scope option was added in P5.2 (see
[Run scope](#run-scope-p52)). Code: `bridges/openlineage/dcp_openlineage/translate.py`.

The table below is the **default** run scope, `trace-process`, unchanged since P4.

## The mapping

| DCP | OpenLineage | Why |
|---|---|---|
| (`trace_id`, `job.host`, `job.pid`, `job.name`) | **One run** | A DCP trace spans processes, but an OpenLineage run belongs to one job. A run is one process's share of one trace |
| run key | `runId = uuid5(DCP_RUN_NAMESPACE, "\|".join(key))` | Deterministic: re-exporting the same events produces the same runs. `DCP_RUN_NAMESPACE` is a fixed UUID in the code; changing it would change every runId ever emitted |
| `job.host`, `job.name` | job `namespace = "dcp://{host}"`, job `name = job.name` | The same script on two hosts is two jobs. A missing host becomes `dcp://unknown-host` |
| read events in the run | `inputs`: unique datasets, sorted | |
| write events in the run | `outputs`: unique datasets, sorted | |
| dataset `namespace` / `name` | copied verbatim | DCP's identity model was designed to match OpenLineage's |
| earliest / latest `ts` in the run | a `START` and a `COMPLETE` event, both carrying the inputs and outputs | See below |
| every DCP event in the run | the `dcp` run facet on the `COMPLETE` event | Carries what the core model cannot (below) |

`COMPLETE` means **the end of the observed window**: the time of the last DCP event in
the run. DCP observes no process exit, so it cannot say the process finished, failed,
or is still running. A long-lived consumer re-exported later, after more events, gets
the same runId and a later `COMPLETE` time.

The translation depends only on the set of events. Identical duplicates count once,
runs are ordered by start time, then job, then runId, and each run's `START` comes
before its `COMPLETE`.

## Why trace → run was rejected

The P0–P3 leaning was "one DCP trace = one OpenLineage run". It does not fit
OpenLineage's model:

- **A run belongs to exactly one job.** A DCP trace deliberately crosses processes:
  in `dark_zone`, `nightly_enrich.py` and `warehouse_loader.py` share one trace,
  because the Kafka header carries it from producer to consumer. That is the
  multi-hop claim working. One run for the trace would need one job for two
  different scripts on possibly two hosts.
- **A long-running process sees many traces.** A consumer that handles two records
  from two producers takes part in two traces. Trace → run would still split it
  correctly, but only because the key also has to include the process. Once the
  process is in the key, the key *is* (trace, process).

So a run is one process's share of one trace. A consumer that handles two traces
becomes two runs of one job; a producer and its consumer that share a trace become
two runs of two jobs.

## What the core model cannot carry, and the `dcp` facet

OpenLineage's core run model lists a run's inputs and outputs. It does not say which
input fed which output, and it cannot say which upstream run fed which downstream run.
Translated naively, two of DCP's precision gains disappear:

- **Within one job**, statement-level precision. A job running
  `INSERT INTO summary SELECT … FROM orders` and
  `INSERT INTO refund_summary SELECT … FROM refunds` becomes one run with two inputs
  and two outputs, which a reader can only take as four edges
  (`benchmarks/ground_truth/job_granularity`).
- **Across jobs**, run-level provenance through a shared topic. Two producers writing
  one topic look identical from the consumer's side
  (`benchmarks/ground_truth/topic_fan_in`).

The `dcp` run facet (`bridges/openlineage/facets/DcpRunFacet.json`) carries every DCP
event of the run, with its parents, so a DCP-aware consumer can rebuild the attested
edges exactly. `benchmarks/ground_truth/score.py` measures both readings.

The facet also carries each event's `ts` and `columns` and the run's DCP `job`
identity (including `pid`). Those are not needed for lineage, but without them the
original envelopes could not be rebuilt exactly; the runId is a hash and cannot be
inverted.

## Trade-offs, stated plainly

- **Run granularity follows DCP, not the scheduler.** A cron job that runs nightly is
  one OpenLineage run per night only if each night is a new process; a single
  long-lived process that handles many traces produces one run per trace.
- **The facet is DCP-specific.** Marquez stores it and shows it as JSON; it does not
  draw the edges from it. Only a DCP-aware reader gets the precision back.
- **No column lineage.** OpenLineage's optional column-lineage facet could carry
  finer-grained lineage than inputs × outputs, but DCP does not do column-level
  lineage (out of v1 scope), so the bridge does not populate it.

## Run scope (P5.2)

`to_openlineage(events, run_scope=...)` and the CLI's `--run-scope` choose which
events form one run:

| Run scope | One run per | runId name |
|---|---|---|
| `trace-process` (**the default**, unchanged) | (`trace_id`, `job.host`, `job.pid`, `job.name`) | `trace_id\|host\|pid\|name` |
| `process` | (`job.host`, `job.pid`, `job.name`) | `process\|host\|pid\|name` |

Both use `uuid5(DCP_RUN_NAMESPACE, name)`. A `trace-process` name starts with a
trace id (DCP emits UUIDs) and a `process` name with the fixed word `process`, so
the two scopes never produce the same runId.

**Why `process` exists.** The paper's OpenLineage baseline must model what
OpenLineage would actually report. A real OpenLineage integration reports one run per
process, with every input and output of that process. The default splits a process
that joins several traces (a consumer reading records from two producers) into
several runs, and inputs × outputs then cannot connect an input in one run to an
output in another. That split is an artefact of this bridge, not of OpenLineage;
P5.1's OpenLineage-core recall loss came from it (see the clarification in
[`docs/results/P5.1.md`](../results/P5.1.md#8-ground-truth-at-scale) and the
per-process results in [`docs/results/P5.2.md`](../results/P5.2.md)).

In `process` scope:

- inputs are every dataset the process read; outputs every dataset it wrote;
- `START` and `COMPLETE` carry the earliest and latest `ts` across the process;
- the `dcp` facet carries every DCP event of the process. Because a process can span
  several traces, the facet adds `trace_ids` (sorted; `trace_id` stays, as the first
  of them) and each event entry its own `trace_id`. Both fields are optional in
  `DcpRunFacet.json`, so every facet written before P5.2 still validates, and the
  default scope never writes them. `reconstruct.py` reads both scopes.

The default stays `trace-process`, so every existing export, test and score is
unchanged.

### Limitation: pid reuse (documented, not worked around)

Two processes with the same job name and the same pid on the same host (an operating
system reusing a pid, say a nightly script that gets pid 4242 two nights running)
**merge into one run** in `process` scope. DCP events carry no process start time, so
nothing in the events can tell them apart. The merged run's inputs × outputs then
joins the two processes' datasets, and its `START`/`COMPLETE` span both. The `dcp`
facet still carries each event with its own parents, so a DCP-aware reader's graph
stays exact. In `trace-process` scope the two stay apart whenever their traces
differ. Tested: `bridges/openlineage/tests/test_bridge_run_scope.py`
(`test_a2_08_pid_reuse_merges_two_processes_into_one_run`). The product fix, a
process start time in the envelope's job identity, is a follow-up in
[`docs/LIMITATIONS.md`](../LIMITATIONS.md).
