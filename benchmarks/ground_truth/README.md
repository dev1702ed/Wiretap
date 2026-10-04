# Ground truth

Answer keys for known workloads. DCP's output is graded against them; DCP
never generates them. An instrument that grades itself measures nothing.

There are two kinds, always scored and reported **apart, never pooled**:

- **Hand-written keys** (one directory each, below): four small workloads,
  each built to discriminate one property. Read-only.
- **Generated keys** (`generated/`, P5.1): larger workloads produced by
  `generate.py` from fixed seeds, with the truth derived from the generator's
  own construction. See [Generated keys](#generated-keys-p51).

Order matters: precision and recall here must land before the adversarial
results mean anything. An instrument not shown to be accurate cannot be used to
measure a gap.

## Workloads

| Directory | Workload | What it tests |
|---|---|---|
| `dark_zone/` | A script reads `orders` and produces to Kafka; a second process consumes and writes `daily_revenue` | Capture, and propagation across a process boundary |
| `topic_fan_in/` | Two producers write one topic; the consumer processes only producer A's record | What propagation adds: run-level precision |
| `job_granularity/` | One job runs two independent `INSERT … SELECT` statements (written by the project owner, P4) | Statement-level precision inside one job, which OpenLineage's core run model (inputs × outputs) cannot express |
| `notebook/` | A Jupyter kernel reads `orders` and writes `summary` through the application (written by the project owner, P5) | Adversarial case 2: a notebook, with no scheduler and no OpenLineage integration |

## Answer-key format (`expected_graph.json`)

| Field | Meaning |
|---|---|
| `processes` | The workload itself: ordered steps per process (`sql`, `produce`, `consume`), and an optional `kind`: `script` (the default) or `notebook`. Tests replay it through DCP's capture code with fakes, treating both kinds the same; `benchmarks/live` runs it live, a `notebook` process as a real notebook |
| `datasets` | Alias → `{namespace, name}`. Names follow the spec (`db.schema.table`) |
| `dataset_edges` | `{from, to, job}` — dataset-level lineage, the unit comparable to OpenLineage |
| `run_edges` | `{from_job, to_job, via}` — which producer run fed which consumer run |
| `provenance` | `{dataset, upstream}` — every dataset the given dataset actually derives from |

## Metrics

For each workload and each level (nodes, dataset edges, run edges, provenance
sets):

- **precision** = |found ∩ expected| / |found|
- **recall** = |found ∩ expected| / |expected|

Target: 1.0 on every level. Capture is deterministic, not inferred, so anything
below 1.0 is a bug rather than a limitation.

## Why two levels

At dataset level, `dark_zone` is just `orders → enriched_orders → daily_revenue`,
which can be reconstructed by matching the shared topic name, with no
propagation at all. If the answer key stopped there, propagation would
contribute nothing measurable.

`topic_fan_in` is built so that it does. Dataset-level reachability gives
`upstream(daily_revenue) = {enriched_orders, orders, refunds}` (precision 2/3);
the truth is `{enriched_orders, orders}`. A tool with dataset-level lineage
only cannot score 1.0 on it. `test_topic_fan_in_discriminates` checks this
property of the answer key itself, so the workload can't silently stop
discriminating.

Producer B runs *before* the consumer, so its record is already on the topic
when the consumer runs. Time ordering therefore cannot rule B out; only the
record's own context can.

`job_granularity` discriminates inside one job. Its run has inputs
`{orders, refunds}` and outputs `{summary, refund_summary}`; read as
inputs × outputs, that is four edges where the truth has two.
`test_job_granularity_discriminates` checks that property of the key.

## Replay, tests, and score

`harness.py` is the one replay implementation. It loads an answer key, runs
each process's steps through DCP's real capture code with faked database and
broker I/O (each process in a fresh `contextvars.Context`, so only record
headers cross between them), and returns the events.

- `sdk-python/tests/test_ground_truth.py` builds the P3 graph from those events
  and requires it to match the key exactly at every level. It is skipped only
  when the backend isn't installed; CI installs it.
- `python benchmarks/ground_truth/score.py` prints precision and recall for
  every level, and a dataset-level baseline row for every provenance entry.
  Results: `docs/results/P3.md`.
- Since P4 it also scores each workload after translation to OpenLineage by
  the bridge (`bridges/openlineage`): the edges and provenance OpenLineage's
  core run model implies, and the provenance a DCP-aware reader recovers from
  the `dcp` run facet. `bridges/openlineage/tests/test_bridge_roundtrip.py`
  pins those numbers. Results: `docs/results/P4.md`.

These are replays, not live runs. Since P5, `benchmarks/live` also runs every key
**live** (real Postgres and Kafka, each process a separate OS process under
`dcp-instrument`) and scores it with the same row functions; `score.py`'s event
source is pluggable (`score_all(events_for)`) and its replay output is pinned byte
for byte by `backend/tests/test_backend_score.py`.

## Generated keys (P5.1)

Four hand-written workloads that each score 1.0 read as a toy. `generate.py`
builds larger ones, in the same answer-key format, and knows the truth because
it decides what every program does.

    python benchmarks/ground_truth/generate.py --write   # regenerate generated/*.json
    python benchmarks/ground_truth/generate.py --check   # verify them byte for byte

| Key | Seed | Jobs |
|---|---|---|
| `generated/scale_s01.json` … `scale_s10.json` | 1 … 10 | 30 each |
| `generated/scale_large.json` | 100 | 100 |

**What a workload contains:** source tables `gen_src_NN (id int, v int)` with
seeded rows; *script* jobs that read tables, produce records to topics and
sometimes insert one row; *consumer* jobs that consume specific named records
and insert one row; *multi-statement* jobs of `INSERT … SELECT` statements;
*notebook* jobs that read tables and insert one row; few topics with many
producers (fan-in); and **distractor reads**: with probability `p_distractor`
(default 0.3) a job reads a table whose values it then does not use.

**The truth is real data flow.** A script's records and inserted row carry
the sum of `v` over the rows of the tables it *uses*, computed by the generator
from the seeded rows and written into the SQL text and the record's name (`r007=412`);
a consumer inserts the sum of the records it consumed. The key credits only
those inputs. Where a job read a distractor before an `INSERT … VALUES` or a
produce, DCP's job-level parenting credits the distractor too, so DCP's
precision drops below 1.0 there. That measures a known limitation; the
generator is never configured to avoid it.

**Not generated, by design:** a job never reads a table another generated job
wrote (store-mediated lineage is out of v1 scope; Postgres reads carry no
parents), and a consumer never reads two records from one topic (job-level
parenting keeps the latest read per dataset). Both are documented v1
limitations, not something the scaled benchmark should rediscover.

**Format additions,** ignored by replay and scoring: a `generated` block
(generator path, version, seed, parameters, `hand_written: false`, and each
job's distractor reads), `tables` (columns and seeded rows) and `topics`, which
`live/seed.py --key` uses to seed a live run. Every process names its `kind`.

**Read-only means the seeds and the generator version.** Rule 3 of
`docs/tasks/P5.md` §2 applies to them, never to hand edits: never edit a
generated key by hand. `benchmarks/tests/test_bench_generate.py` checks that
every committed key regenerates byte for byte, that the truth derivation
matches hand-checked expectations on tiny workloads, and that the generated
programs contain no DCP code. The files are committed with `-text`
(`.gitattributes`), so a Windows checkout keeps their exact bytes.

**Scoring** (`scale.py`, the `scale` stage of `benchmarks/run.py`): each key is
scored with `score.py`'s own row functions, then grouped by method (DCP
run-level, the dataset-level baseline, OpenLineage's core model, OpenLineage
with the `dcp` facet) and level (nodes, dataset edges, run edges, provenance),
and micro-averaged across the seeds, with the per-key distribution. `scale_large`
is reported on its own. Every item DCP finds beyond the truth is checked
against the generator's distractor reads, and any recall below 1.0 is listed.
Replay covers every key; live covers every key in full mode and `scale_s01`
only in quick mode (CI).
