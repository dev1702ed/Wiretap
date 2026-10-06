# The OpenLineage baseline, verified (P5)

Every "OpenLineage misses this" claim in this suite is made against **every
OpenLineage integration available for the workload's stack, installed, with zero
code changes to the workload**. This file checks that baseline against the
OpenLineage repository at **tag `1.53.0`** (commit
`8ad5c14c63fbab63fedd8ff42f9a208d86ad07fe`), the release whose spec P4 vendored,
and then measures it.

The stack in question: a plain Python script, or a Jupyter notebook, that uses
**psycopg** (Postgres) and **confluent-kafka** (Kafka) directly.

## 1. The integrations that exist at 1.53.0

From the repository tree (`integration/`, `client/`) and the integrations section
of the documentation at the same tag (`website/docs/integrations/`):

| Integration | Where | How it captures | Captures psycopg / confluent-kafka in a plain script, no code changes? |
|---|---|---|---|
| Apache Spark | [`integration/spark`](https://github.com/OpenLineage/OpenLineage/tree/1.53.0/integration/spark) (+ [`spark-extension-interfaces`](https://github.com/OpenLineage/OpenLineage/tree/1.53.0/integration/spark-extension-interfaces), [`spark-extension-entrypoint`](https://github.com/OpenLineage/OpenLineage/tree/1.53.0/integration/spark-extension-entrypoint)) | A `SparkListener` in the Spark JVM | No: only jobs run by Spark |
| Apache Flink | [`integration/flink`](https://github.com/OpenLineage/OpenLineage/tree/1.53.0/integration/flink) | A job listener in the Flink JVM | No: only Flink jobs |
| Apache Hive | [`integration/hive`](https://github.com/OpenLineage/OpenLineage/tree/1.53.0/integration/hive) | A JVM hook in Hive | No: only Hive queries |
| dbt | [`integration/dbt`](https://github.com/OpenLineage/OpenLineage/tree/1.53.0/integration/dbt) | The `dbt-ol` wrapper parses dbt's artifacts and structured logs | No: only dbt runs. dbt-postgres uses a Postgres driver internally, but the lineage comes from dbt's model graph, not from the driver |
| Apache Airflow | [docs page at the tag](https://github.com/OpenLineage/OpenLineage/blob/1.53.0/website/docs/integrations/airflow.md); maintained as [`apache-airflow-providers-openlineage`](https://airflow.apache.org/docs/apache-airflow-providers-openlineage/stable/index.html) in the Airflow repository | Operator extractors and hook-level lineage inside Airflow tasks | No: only code running as an Airflow task through Airflow operators or hooks. Moving a script into Airflow is a code change |
| Trino | [docs page at the tag](https://github.com/OpenLineage/OpenLineage/blob/1.53.0/website/docs/integrations/trino.md) | An event listener plugin in the Trino coordinator | No: only queries Trino executes |
| Presto | [docs page at the tag](https://github.com/OpenLineage/OpenLineage/blob/1.53.0/website/docs/integrations/presto.md) | An event listener in Presto | No: only queries Presto executes |
| Great Expectations | [docs page at the tag](https://github.com/OpenLineage/OpenLineage/blob/1.53.0/website/docs/integrations/great-expectations.md) | An action in a checkpoint | No: data-quality runs only |
| Feast | [docs page at the tag](https://github.com/OpenLineage/OpenLineage/blob/1.53.0/website/docs/integrations/feast.md) | Emitted by Feast itself on `feast apply` / `feast materialize` | No: feature-store operations only |
| `openlineage-integration-common` | [`integration/common`](https://github.com/OpenLineage/OpenLineage/tree/1.53.0/integration/common) | A library for integrations (BigQuery, Redshift Data API, Snowflake, dbt, Great Expectations providers) | No: a library other integrations call. Its source has no psycopg or confluent-kafka capture |
| `openlineage-sql` | [`integration/sql`](https://github.com/OpenLineage/OpenLineage/tree/1.53.0/integration/sql) | A SQL parser library (Rust, with Python and Java bindings) | No: it parses SQL it is given. Something has to hand it the query |
| `openlineage-python` | [`client/python`](https://github.com/OpenLineage/OpenLineage/tree/1.53.0/client/python) | A client for **manual emission** (§2) | No: it emits only what the author constructs. Its `transport/kafka.py` uses confluent-kafka to *send* OpenLineage events to Kafka; it does not observe the application's Kafka traffic |
| Java and Go clients | [`client/java`](https://github.com/OpenLineage/OpenLineage/tree/1.53.0/client/java), [`client/go`](https://github.com/OpenLineage/OpenLineage/tree/1.53.0/client/go) | Manual emission | Not Python |

How this was checked: the tree at the tag was listed, and the Python sources of
`client/python/src` and `integration/common` were searched for `psycopg`,
`confluent_kafka`, `confluent-kafka`, `kafka-python`, `sitecustomize`, and
monkeypatching. The only hits were the Kafka *transport* above and dbt test
fixtures (logs from dbt-postgres runs).

**Result: none of them captures psycopg or confluent-kafka in a plain Python
script or a notebook without code changes.** The baseline graph for adversarial
cases 1 and 2 is empty, and §3 measures it.

## 2. What manual emission requires

`openlineage-python` offers lineage the author **declares**. To report what
dark_zone's producer does, the author must, in the script:

1. create a client (`OpenLineageClient()`, which reads `OPENLINEAGE_URL` or
   `openlineage.yml`);
2. invent a run id and choose a job namespace and name;
3. name **every** input and output dataset in OpenLineage's naming
   (`InputDataset("postgres://localhost:5432", "dcp.public.orders")`,
   `OutputDataset("kafka://localhost:9092", "enriched_orders")`);
4. build and `emit()` a `RunEvent` for `START` and another for `COMPLETE`.

[`manual_emission.py`](manual_emission.py) is exactly that, for dark_zone's
producer. Nothing checks that the declared datasets are the ones the code touched,
and it says nothing about which input fed which output, or which upstream run fed
which downstream run. DCP observes the queries and records instead: **attested,
not declared**.

## 3. Measured: what reaches a lineage server with no code changes

[`baseline_check.py`](baseline_check.py), run by `python benchmarks/run.py` as
part of the `adversarial` stage:

1. starts a stub HTTP server that counts every request, on any path;
2. runs dark_zone's generated scripts and the notebook workload's notebook (the
   same programs the live harness runs under `dcp-instrument`) **without**
   `dcp-instrument`, with `openlineage-python` installed and `OPENLINEAGE_URL`
   pointing at the stub;
3. as a positive control, runs `manual_emission.py` with the same
   `OPENLINEAGE_URL`. It must deliver its two events, otherwise a count of 0
   could just mean a broken stub.

Expected: 0 events from the uninstrumented programs. The measured counts are in
the generated results, verbatim: `docs/results/P5-sandbox.md` (this sandbox),
the CI job summary (`--label ci`), and the owner's machine's records
(`docs/results/P5-local.md`, and the final run, `docs/results/P5-local-final.md`, which the
evidence pack cites as claim C1), under "Adversarial".

## 4. How the claim narrows — stated plainly

- **Cases 1 and 2 are a gap in the ecosystem at 1.53.0, not a theorem.** No
  OpenLineage integration intercepts client libraries in a plain process. One
  *could* be written: patching psycopg and confluent-kafka in-process is what DCP
  itself does, and DCP's events reach OpenLineage through the P4 bridge. So the
  precise claim is: with every OpenLineage integration that exists installed and
  no code changes, a plain script or notebook produces **no lineage at all**, and
  manual emission produces only **declared** lineage. "Structural" refers to how
  OpenLineage's integrations are built (hooks in engines, orchestrators and
  frameworks), which leaves code outside any framework unobserved.
- **Case 3, and job-level precision, are limits of the core run model itself.**
  However lineage reaches OpenLineage, a run carries inputs and outputs, not
  which input fed which output or which upstream run fed which downstream run.
  P4 measured both losses on `topic_fan_in` and `job_granularity` (the
  `openlineage …` rows of `score.py`'s output, in `docs/results/P4.md`, and live
  in the P5 results). That holds for any producer that emits
  core run events, including a hypothetical psycopg integration. The optional
  column-lineage facet can carry finer lineage when an integration fills it in;
  none does for these libraries.
- **The interception technique is not new.** OpenTelemetry's
  `opentelemetry-instrument` patches psycopg and confluent-kafka with no code
  changes, and propagates trace context through Kafka headers, which is the
  pattern `dcp-instrument` follows. OpenTelemetry produces traces, not lineage:
  it has no dataset identity model and no read-to-write parentage. A determined
  user could derive lineage from those spans, and that would be a new integration.
