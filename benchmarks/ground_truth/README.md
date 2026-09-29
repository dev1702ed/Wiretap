# Ground truth

Hand-written answer keys for known workloads. DCP's output is graded against
them; DCP never generates them. An instrument that grades itself measures
nothing.

Order matters: precision and recall here must land before the adversarial
results mean anything. An instrument not shown to be accurate cannot be used to
measure a gap.

## Workloads

| Directory | Workload | What it tests |
|---|---|---|
| `dark_zone/` | A script reads `orders` and produces to Kafka; a second process consumes and writes `daily_revenue` | Capture, and propagation across a process boundary |
| `topic_fan_in/` | Two producers write one topic; the consumer processes only producer A's record | What propagation adds: run-level precision |

## Answer-key format (`expected_graph.json`)

| Field | Meaning |
|---|---|
| `processes` | The workload itself: ordered steps per process (`sql`, `produce`, `consume`). Tests replay it through DCP's capture code with fakes; P5 replays it live |
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

These are replays, not live runs. Live replay against Postgres and Kafka is P5.
