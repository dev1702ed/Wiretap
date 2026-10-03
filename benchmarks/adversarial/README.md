# Adversarial suite

Data movements application-layer lineage structurally cannot see, and lineage
questions it cannot answer precisely.

## The baseline, stated exactly

Every "OpenLineage misses this" claim is made against this configuration:
**every OpenLineage integration available for the workload's stack, installed,
with zero code changes to the workload itself.** For a plain Python script
using psycopg and confluent-kafka, no such integration exists, so the baseline
graph is empty. Say it in those words; never imply OpenLineage was merely
misconfigured.

[`BASELINE.md`](BASELINE.md) verifies this against the OpenLineage repository at
tag 1.53.0 (every integration listed, with links), says exactly what manual
emission requires, measures the baseline empirically, and states how the claim
narrows.

## Cases

| # | Movement | Why the baseline misses it | Gap |
|---|---|---|---|
| 1 | Ad-hoc script: Postgres read → Kafka produce | No integration exists for a plain script. OpenLineage *can* be added by hand, but only by declaring the datasets: lineage the author asserts, not lineage that was observed. DCP needs **no code changes** (`dcp-instrument`) | **No code changes**: declared vs. attested |
| 2 | Jupyter notebook doing the same | As case 1; notebook kernels are not orchestrated jobs | No code changes: declared vs. attested |
| 3 | Two producers share a topic; the consumer processes only one producer's record | Dataset-level lineage says the sink derives from both producers' inputs. Only per-record context says which | Precision — run-level provenance. Ground truth: `topic_fan_in` |
| 4 | Dynamic table names built at runtime (`psycopg.sql`) | Static SQL analysis sees a template; DCP sees the executed statement | **Candidate — not claimed.** Verify against OpenLineage's SQL parser first |

### Executable form

The ground-truth workloads are these cases' tests, so there is one source of
truth rather than two. Since P5 each one also runs **live**
(`benchmarks/live`): real PostgreSQL and Kafka, each process a separate OS
process under `dcp-instrument`, programs generated with **no DCP code in them**
and kept with the results.

| Case | Workload | Replay (faked I/O) | Live evidence |
|---|---|---|---|
| 1 | `ground_truth/dark_zone` | Since P3 | Two generated scripts, no DCP code, under `dcp-instrument`; scored against the key |
| 2 | `ground_truth/notebook` (P5) | Since P5 | A generated notebook, no DCP code, executed by `nbclient` in a kernel started with `dcp-instrument`'s environment; scored against the key |
| 3 | `ground_truth/topic_fan_in` | Since P3 | Three generated scripts; the consumer **checks the record it reads is producer A's** and fails loudly otherwise; scored against the key, with the dataset-level baseline row alongside |
| 4 | none — not claimed | — | — |

The live results are generated, never typed: `python benchmarks/run.py --label
<label>` writes them to `docs/results/P5-<label>.md` (`sandbox`: this repo's
sandbox run; `ci`: the CI `live` job's summary; `local`: the owner's machine).
The baseline side is measured too: `baseline_check.py` runs the same programs
without `dcp-instrument` against a stub OpenLineage endpoint and counts what
arrives (BASELINE.md §3).

### What decision 6 changes

Decision 6 is closed (P5): `dcp-instrument python script.py` captures a script
that contains **no DCP code at all**. DCP's `sitecustomize` initialises and
patches at interpreter start-up, configured by environment variables, so the
script is literally untouched. Cases 1 and 2 are therefore claimed as
**"no code changes"**: DCP attests lineage the author never declared, whereas
manual OpenLineage emission requires the author to name every dataset.

The explicit two-line form (`dcp.init()` plus `dcp.patch_*()`) remains, and for
it the earlier framing still holds: those lines are generic and say nothing
about which datasets the script touches.

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
| Import order (explicit calls only) | `patch_kafka()` must run before `from confluent_kafka import Producer`. `dcp-instrument` removes this hazard: it patches before any user import |

## Honest test for each case

Before claiming a case, ask: could a determined OpenLineage user cover this by
writing one more integration? If yes, it's a configuration gap and it doesn't
belong here. Ship fewer, stronger cases.
