# Known limitations of DCP v1

Every known limitation and follow-up from P3 to P5.2, in one place. The paper's
limitations section is written from this file. For each one: **what** it is,
**where it was found**, whether it is **measured** (and if so the number, quoted
verbatim from its record, with a link), and the **product follow-up** that would
address it. Quoted tables are copied from the records by a script, never retyped.

Nothing here was fixed in P5.2: P5.2 changed measurement, translation, docs and
release metadata only (its rules forbid product changes), so every product
follow-up below is open.

## 1. Capture: what DCP's events cannot say

### 1.1 Store-mediated lineage is not inferred

- **What.** Job A writes a table and job B later reads it. Postgres rows carry no
  per-record metadata, so B's read has `parent: []`, and DCP's run-level provenance
  stops at the table. The dataset-level graph joins the two only through the shared
  table node.
- **Found.** By design since P3 ([`P3.md`, §7](results/P3.md#7-known-limitations-and-follow-ups);
  repeated in [`P5.md`, §12](results/P5.md#12-known-limitations-and-follow-ups)).
- **Measured** (P5.2, the stress set: store-read jobs, chains of length 1 and 2). Misses
  per cause, verbatim from [`P5-p52-stress.md`](results/P5-p52-stress.md) (stress set,
  live; replay is identical):

| Key | DCP run-level misses | DCP: multi-record consumer: earlier record's parent dropped (job-level keeps the latest read per dataset) | DCP: store-mediated: Postgres read carries no parents | OpenLineage + dcp facet misses (same causes) | OpenLineage core (trace-process): split run | Unexplained |
|---|---|---|---|---|---|---|
| stress_large | 57 | 8 | 49 | 57 | 19 | 0 |
| stress_s01 | 13 | 3 | 10 | 13 | 5 | 0 |
| stress_s02 | 13 | 1 | 12 | 13 | 6 | 0 |
| stress_s03 | 13 | 0 | 13 | 13 | 4 | 0 |
| stress_s04 | 6 | 0 | 6 | 6 | 9 | 0 |
| stress_s05 | 10 | 2 | 8 | 10 | 5 | 0 |
| **stress_s01 … stress_s05, total** | 55 | 6 | 49 | 55 | 29 | 0 |

  The same record's micro-averaged provenance rows over `stress_s01` … `stress_s05`
  (live), with the dataset-level baseline, which crosses tables and so keeps every
  item, at lower precision:

| Method | Level | Precision | Recall | Keys | Per-key precision min / median / max | Per-key recall min / median / max |
|---|---|---|---|---|---|---|
| DCP run-level | provenance | 402/452 = 0.889 | 402/457 = 0.880 | 5 | 0.849 / 0.872 / 0.942 | 0.852 / 0.870 / 0.935 |
| dataset-level baseline | provenance | 457/640 = 0.714 | 457/457 = 1.000 | 5 | 0.686 / 0.702 / 0.752 | 1.000 / 1.000 / 1.000 |
| OpenLineage + dcp facet | provenance | 402/452 = 0.889 | 402/457 = 0.880 | 5 | 0.849 / 0.872 / 0.942 | 0.852 / 0.870 / 0.935 |

- **Follow-up.** Infer store-mediated links as a separate, labelled edge class (a write
  to a table, then a later read of it by another job), never mixed into attested edges,
  and score inferred edges separately. A stronger alternative is per-row metadata (a
  provenance column), which changes the user's schema and is out of v1's scope.

### 1.2 A consumer that reads several records from one topic keeps only the last

- **What.** Job-level parenting keeps the **latest read per dataset**. A consumer that
  consumes several records from one topic and writes from all of them is parented to
  the last record only, so the earlier records' producers' inputs drop out of its
  write's provenance.
- **Found.** Documented in P3 ("only the last record of a `consume()` batch parents
  later writes", [`P3.md`, §7](results/P3.md#7-known-limitations-and-follow-ups)) and
  excluded from the P5.1 generator ([`P5.1.md`, §12, assumption 15](results/P5.1.md#12-assumptions--needs-review)).
- **Measured** (P5.2): the *multi-record consumer* column of the per-cause table in §1.1.
- **Follow-up.** Keep every read of a dataset since the job's last write (a bounded set
  per dataset) instead of the latest one, so a write is parented to all the records it
  may have used. That trades some precision (records read but not used) for recall;
  measure both on the stress set.

### 1.3 Job-level parenting over-approximates

- **What.** A write whose statement names no sources (`INSERT … VALUES`, a Kafka
  produce) is parented to the latest read of **every** dataset the job read earlier,
  including reads whose values were never used (distractor reads). `INSERT … SELECT`
  is exact.
- **Found.** By design (P3's event model); measured from P5.1 on.
- **Measured.** Every extra item DCP reports at scale is a distractor read. Verbatim,
  `scale_s01` … `scale_s10`, live, from [`P5-p52-stress.md`](results/P5-p52-stress.md):

| Method | Level | Precision | Recall | Keys | Per-key precision min / median / max | Per-key recall min / median / max |
|---|---|---|---|---|---|---|
| DCP run-level | dataset edges | 794/896 = 0.886 | 794/794 = 1.000 | 10 | 0.854 / 0.878 / 0.938 | 1.000 / 1.000 / 1.000 |
| DCP run-level | provenance | 891/995 = 0.895 | 891/891 = 1.000 | 10 | 0.856 / 0.903 / 0.933 | 1.000 / 1.000 / 1.000 |

- **Follow-up.** Only payload or data-flow analysis can tell a used read from an unused
  one; out of v1's scope. A lighter option is an explicit scoping API (a context
  manager that ends the job-level read set), opt-in.

### 1.4 Other capture gaps (not measured)

| What | Found | Follow-up |
|---|---|---|
| Reads in worker threads do not parent writes made later in the calling thread (the one remaining xfail, `test_threads.py`) | [`P3.md`, §7](results/P3.md#7-known-limitations-and-follow-ups) | Merge a worker's read set back into the submitting context when its future completes (`patch_threadpool`) |
| A batch `consume()` adopts the last record's trace | [`P5.md`, §12](results/P5.md#12-known-limitations-and-follow-ups) | Record every record's trace and parents on the batch read |
| `executemany()` and `copy()` are not intercepted; `SerializingProducer`/`DeserializingConsumer` are not covered | [`P3.md`, §7](results/P3.md#7-known-limitations-and-follow-ups), [`P5.md`, §12](results/P5.md#12-known-limitations-and-follow-ups) | Wrap them as `execute`, `produce` and `poll` are wrapped |
| Kafka writes are attested at `produce()`, not at the broker's acknowledgement | [`P3.md`, §7](results/P3.md#7-known-limitations-and-follow-ups) | Emit the write from the delivery callback, or mark undelivered writes |
| A quoted Postgres identifier containing a `.` can be mis-qualified (names are qualified by structure) | [`P3.md`, §7](results/P3.md#7-known-limitations-and-follow-ups) | Qualify from sqlglot's parsed identifiers only |
| The CTE fix is statement-wide, not scope-aware | [`P5.md`, §12](results/P5.md#12-known-limitations-and-follow-ups) | Resolve CTE names per scope |
| `python -I`, `-E` and `-S` run uninstrumented; the default `console` sink writes events to the program's stdout | [`P5.md`, §12](results/P5.md#12-known-limitations-and-follow-ups) | Document; default to a file sink under `dcp-instrument` |
| Column names only, no column-to-column lineage | v1 scope ([`README.md`](../README.md)) | A column-lineage facet, once DCP has column lineage |
| Kafka namespaces come from `bootstrap.servers`: clients listing different brokers of one cluster fragment | [`docs/decisions/identity.md`](decisions/identity.md) | Use the cluster ID as the namespace |
| `localhost` is never canonicalised: the same host seen as `localhost` and by name are two datasets | [`docs/decisions/identity.md`](decisions/identity.md) | An explicit identity alias map |

## 2. Overhead

### 2.1 The < 2% throughput target is not met against sub-millisecond queries

- **What.** DCP adds a fixed cost per call. Against the benchmark's local,
  sub-millisecond queries that cost is far more than 2% of throughput.
- **Found.** P5 ([`P5.md`](results/P5.md)); restated as a fixed cost in
  [`P5.1.md`, §7](results/P5.1.md#7-throughput-and-the-fixed-cost-per-call).
- **Measured.** Verbatim (selected rows, the `file` sink), from
  [`P5-p51-final-comparison.md`](results/P5-p51-final-comparison.md), the sandbox:

| Tier | Config | Implied µs/call [95% CI] | Loss < 2% for queries slower than (µs) | Loss at a 1 ms query | Loss at a 10 ms query | Loss at a 100 ms query |
|---|---|---|---|---|---|---|
| T1 point read | file | +72.4 [+63.8, +81.0] | 3546.1 | 6.75% | 0.72% | 0.07% |
| T5 analytical | file | +104.6 [+95.8, +113.3] | 5125.4 | 9.47% | 1.04% | 0.10% |
| L5 analytical, literal (added in P5.1) | file | +257.8 [+235.3, +281.7] | 12631.1 | 20.49% | 2.51% | 0.26% |

  The owner's full-mode run on the final code is pending ([`RUNBOOK.md`](RUNBOOK.md),
  step 4); the evidence pack and the figures switch to it when it is committed.
- **Follow-up.** Less Python work per event (IDs, timestamps, capture's own logic);
  moving work to a thread does not reduce the cost per call.

### 2.2 The SQL comment and the HTTP enqueue are not optimised

- **What.** Each is attributed above 10 µs on some tiers and was left as is.
- **Found.** [`P5.1.md`, §13](results/P5.1.md#13-known-limitations-and-follow-ups).
- **Measured.** Verbatim, T1, from [`P5-p51-after-final.md`](results/P5-p51-after-final.md):

| Component | Measured as | p50 µs [95% CI] | Implied µs/call [95% CI] |
|---|---|---|---|
| wrapper | `wrap-only` | +1.0 [-4.1, +6.5] | +5.3 [-0.4, +10.9] |
| capture + construction | `capture-null − wrap-only` | +41.0 [+30.0, +53.4] | +39.2 [+30.3, +49.1] |
| async enqueue | `http-down − capture-null` | +2.2 [-7.9, +12.7] | +2.0 [-6.3, +10.9] |
| synchronous file write | `file − http-down` | +19.6 [+5.5, +33.2] | +25.8 [+13.3, +37.1] |
| SQL comment | `file+sqlcomment − file` | +16.6 [+10.5, +22.6] | +16.5 [+10.0, +23.9] |

- **Follow-up.** Build the comment string once per trace; batch the enqueue.

### 2.3 Start-up

- **What.** `dcp-instrument` starts a second interpreter; a program that imports
  psycopg and confluent-kafka pays for them as it would without DCP.
- **Found.** P5; reduced in P5.1 (lazy patching), [`P5.1.md`, §6](results/P5.1.md#6-start-up-before-and-after).
- **Measured.** Verbatim, from [`P5-p51-final-comparison.md`](results/P5-p51-final-comparison.md):

| Command | p50 before | after | p95 before | after |
|---|---|---|---|---|
| python | 14.1 | 14.7 | 15.5 | 20.1 |
| dcp-instrument python | 432.2 | 101.2 | 453.9 | 124.2 |
| python with DCP's sitecustomize | 264.5 | 59.2 | 315.3 | 71.0 |
| python, importing psycopg and confluent_kafka (added in P5.1) | 183.9 | 200.6 | 201.1 | 243.6 |
| dcp-instrument python, importing psycopg and confluent_kafka (added in P5.1) | 421.7 | 250.7 | 482.5 | 293.0 |

- **Follow-up.** An in-process launcher (cut in P5.1: it cannot keep start-up semantics
  exactly, see [`P5.1.md`, §11](results/P5.1.md#11-decisions-made)).

### 2.4 Not explained function by function; other notes

| What | Found | Follow-up |
|---|---|---|
| The gap between the CPU microbenchmark (4a) and the real path is named as capture on the real path, not explained function by function | [`P5.1.md`, §13](results/P5.1.md#13-known-limitations-and-follow-ups) | A sampling profiler |
| The literal-normalised cache gives an unparseable text its parseable sibling's tables (a recall gain only on text sqlglot cannot parse) | [`P5.1.md`, §12, assumption 9](results/P5.1.md#12-assumptions--needs-review) | Test against a corpus with such pairs |
| CI's quick-mode overhead numbers come from shared runners and are noisy | [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | None: the owner's machine is the authoritative source |

## 3. Backend

| What | Found | Follow-up |
|---|---|---|
| The graph is in memory and grows with every event; `/graph` has no pagination; `upstream` walks the whole history | [`P3.md`, §7](results/P3.md#7-known-limitations-and-follow-ups) | A persistent graph store; windowed queries |
| The backend must run as one process (one uvicorn worker); one SQLite connection behind a lock caps ingest | [`P3.md`, §7](results/P3.md#7-known-limitations-and-follow-ups) | A shared store and a fold per worker |
| The HTTP sink drops events under sustained overload (counted, but the graph disconnects); a `422` rejects a whole batch; no HTTPS or authentication | [`P3.md`, §7](results/P3.md#7-known-limitations-and-follow-ups) | Back-pressure policy per deployment; TLS and auth |
| Events still queued when a process is killed (SIGKILL, `os._exit`) are lost | [`P3.md`, §7](results/P3.md#7-known-limitations-and-follow-ups) | The file sink, which writes before each call returns, where this matters |
| The FastAPI app still reports version `0.1.0.dev0` (`backend/app/main.py`): P5.2 could change only `__version__` lines under `backend/app/`, and it has none | P5.2 ([`P5.2.md`, §8](results/P5.2.md#8-assumptions--needs-review)) | Read the version from package metadata |

## 4. The OpenLineage bridge

### 4.1 The default run mapping splits a process that joins several traces

- **What.** The default run scope, `trace-process`, maps one OpenLineage run per (trace,
  process). A consumer that joins two traces becomes two runs, and OpenLineage's core
  model (inputs × outputs per run) then loses the link from one run's input to the
  other's output.
- **Found.** [`P5.1.md`, §8](results/P5.1.md#8-ground-truth-at-scale) (with its P5.2
  clarification).
- **Measured.** Verbatim, `scale_s01` … `scale_s10`, live, from
  [`P5-p52-mapping.md`](results/P5-p52-mapping.md), next to the `process` scope P5.2 added:

| Method | Level | Precision | Recall | Keys | Per-key precision min / median / max | Per-key recall min / median / max |
|---|---|---|---|---|---|---|
| OpenLineage core | dataset edges | 758/1340 = 0.566 | 758/794 = 0.955 | 10 | 0.533 / 0.565 / 0.598 | 0.940 / 0.952 / 0.976 |
| OpenLineage core | provenance | 842/1736 = 0.485 | 842/891 = 0.945 | 10 | 0.449 / 0.484 / 0.517 | 0.900 / 0.944 / 0.967 |
| OpenLineage core (per process) | dataset edges | 794/1392 = 0.570 | 794/794 = 1.000 | 10 | 0.539 / 0.572 / 0.610 | 1.000 / 1.000 / 1.000 |
| OpenLineage core (per process) | provenance | 891/1855 = 0.480 | 891/891 = 1.000 | 10 | 0.448 / 0.479 / 0.519 | 1.000 / 1.000 / 1.000 |

- **Follow-up.** P5.2 added `--run-scope process` (one run per process). Whether it
  should become the default is a product decision: it models OpenLineage integrations,
  at the price of the pid-reuse merge (4.2).

### 4.2 `process` scope merges two processes that reuse a pid

- **What.** Two processes with the same job name and pid on the same host merge into one
  run: DCP events carry no process start time.
- **Found.** P5.2 ([`docs/decisions/openlineage-mapping.md`](decisions/openlineage-mapping.md#limitation-pid-reuse-documented-not-worked-around));
  tested in `bridges/openlineage/tests/test_bridge_run_scope.py`.
- **Measured.** No: it cannot occur in the benchmarks (every process has its own name).
- **Follow-up.** Add the process start time to the envelope's job identity (a spec
  change) and to the run key.

### 4.3 Other bridge limitations

| What | Found | Follow-up |
|---|---|---|
| The `dcp` run facet grows without bound in a long-running process | [`P5.md`, §12](results/P5.md#12-known-limitations-and-follow-ups) | Cap it, or chunk it across events |
| Marquez stores the facet but draws edges from inputs and outputs only | [`P4.md`, §8](results/P4.md#8-known-limitations-and-follow-ups) | A Marquez (or DataHub) plugin that reads the facet |
| `COMPLETE` is the end of the observed window; DCP never emits `FAIL` or `ABORT` | [`P4.md`, §8](results/P4.md#8-known-limitations-and-follow-ups) | Observe process exit (an `atexit` event) |
| The transport POSTs one event at a time | [`P4.md`, §8](results/P4.md#8-known-limitations-and-follow-ups) | Batching, for a live sink |

## 5. The evaluation itself

| What | Found | Measured | Follow-up |
|---|---|---|---|
| The generated keys never give a script's outputs different subsets of its reads | [`P5.1.md`, §12, assumption 16](results/P5.1.md#12-assumptions--needs-review) | No | A generator option, scored apart as the stress set is |
| Multi-record consumers are rare in the stress set (`p_multi_record` 0.15 per consumer): the counts behind that cause are small | P5.2 ([`P5.2.md`](results/P5.2.md#4-the-stress-set)) | Yes: the per-cause table in §1.1 | Generate more keys, or a set with that kind alone |
| The dynamic-table-name adversarial candidate (case 4) is unclaimed | [`docs/tasks/P5.md`](tasks/P5.md) | No | Build it as an answer key |
| Kafka broker versions are declared (`DCP_BENCH_KAFKA_VERSION`), not detected | [`P5.md`, §12](results/P5.md#12-known-limitations-and-follow-ups) | No | Read it from the broker's logs or admin API |
| The pinned `networkx==3.7` does not install on Python 3.11 (the pins cover 3.10 and 3.12+) | P5.2 ([`P5.2.md`, §8](results/P5.2.md#8-assumptions--needs-review)) | No | Add a 3.11 pin line |
| Every hand-written and generated key is replayed with one job identity per process name (host `bench`, pid 1); live runs use real pids | `benchmarks/ground_truth/harness.py` | No | None needed: live runs cover real identities |

## 6. Owner steps still open (not limitations of the code)

These are in [`docs/RUNBOOK.md`](RUNBOOK.md), with exact commands: the full-mode overhead
run on the final code (step 4); the dark-zone demo's timing and the Marquez check (step 7; the demo itself ran
end to end once in the P5.2 sandbox, untimed); the owner's name in `CITATION.cff` (step 9); the release and
its DOI (step 10); publishing, optional, under a different distribution name because
`dcp` is taken on PyPI (step 11; [`V1.md`](results/V1.md#packaging-c2)).
