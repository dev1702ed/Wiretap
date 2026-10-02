# Adversarial suite

Data movements application-layer lineage structurally cannot see, and lineage
questions it cannot answer precisely.

## The baseline, stated exactly

Every "OpenLineage misses this" claim is made against this configuration:
**every OpenLineage integration available for the workload's stack, installed,
with zero code changes to the workload itself.** For a plain Python script
using psycopg and confluent-kafka, no such integration exists, so the baseline
graph is empty by construction. That emptiness is the structural claim. Say it
in those words; never imply OpenLineage was merely misconfigured.

## Cases

| # | Movement | Why the baseline misses it | Gap |
|---|---|---|---|
| 1 | Ad-hoc script: Postgres read → Kafka produce | No integration exists for a plain script. OpenLineage *can* be added by hand, but only by declaring the datasets: lineage the author asserts, not lineage that was observed | Structural — **declared vs. attested** |
| 2 | Jupyter notebook doing the same | As case 1; notebook kernels are not orchestrated jobs | Structural — declared vs. attested |
| 3 | Two producers share a topic; the consumer processes only one producer's record | Dataset-level lineage says the sink derives from both producers' inputs. Only per-record context says which | Precision — run-level provenance. Ground truth: `topic_fan_in` |
| 4 | Dynamic table names built at runtime (`psycopg.sql`) | Static SQL analysis sees a template; DCP sees the executed statement | **Candidate — not claimed.** Verify against OpenLineage's SQL parser first |

### Executable form

The ground-truth workloads are these cases' tests, so there is one source of
truth rather than two:

| Case | Workload | State |
|---|---|---|
| 1 | `ground_truth/dark_zone` | Passes on replay with faked I/O (P3); live run is P5 |
| 2 | needs a notebook workload | P5 |
| 3 | `ground_truth/topic_fan_in` | Passes on replay with faked I/O (P3); live run is P5 |
| 4 | none — not claimed | — |

The baseline side needs no test: with no integration for the stack, the
OpenLineage graph is empty by construction.

### What decision 6 changes

Cases 1 and 2 currently need two lines in the script (`dcp.init()` and a
`dcp.patch_*()` call). The honest claim is therefore *declared vs. attested*:
those lines are generic and say nothing about which datasets the script touches,
whereas manual OpenLineage emission requires naming them. Zero-code
auto-instrumentation (decision 6) would leave the script literally untouched
and strengthen the claim to "no code changes at all."

## Known limitations — NOT adversarial cases

Movements DCP v1 also misses, or captures imprecisely. Listed so nobody claims
them.

| Limitation | Why |
|---|---|
| `psql` / CLI `COPY` | C binary; an in-process Python interceptor cannot see it (a sidecar or eBPF could) |
| Non-Python services | Same reason |
| `cursor.executemany()`, `cursor.copy()` | Not intercepted in v1 |
| Write → later read through a Postgres table | Rows carry no per-record metadata, so nothing attests this link. The dataset-level graph joins the two only through the shared table node; run-level provenance (`upstream`) stops at the table, and P3 infers no such links |
| Batch `consume()` | The batch adopts the trace of its last record, and only that record's edge parents later writes |
| Reads inside `ThreadPoolExecutor` workers | The trace follows the work, but the context copy is one-way, so worker reads don't parent writes made after the pool returns |
| Kafka writes | Attested at `produce()`, not at broker acknowledgement |
| `SerializingProducer` / `DeserializingConsumer` | Bind the original C types at import; not covered |
| Import order | `patch_kafka()` must run before `from confluent_kafka import Producer` |

## Honest test for each case

Before claiming a case, ask: could a determined OpenLineage user cover this by
writing one more integration? If yes, it's a configuration gap and it doesn't
belong here. Ship fewer, stronger cases.
