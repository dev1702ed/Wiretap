# Adversarial suite

Data movements that application-layer lineage provably cannot see.

## Candidate cases (P0: turn these into failing tests)

| # | Movement | Why app-layer misses it | Structural or config gap? |
|---|---|---|---|
| 1 | Ad-hoc `.py` script: read Postgres → write Kafka | No framework, so no plugin exists to instrument | **Structural** — headline case |
| 2 | Jupyter notebook doing the same | Notebook kernels are not orchestrated jobs | **Structural** |
| 3 | Internal microservice writing to a table directly | Not in any scheduler's DAG | **Structural** |
| 4 | `psql` / CLI-driven `COPY` | No application to instrument at all | **Structural** |

Cases 1 and 4 are the strongest: there is no plugin that *could* exist, not merely one that
was not installed.

## Honest test for each case

Before claiming a case, ask: could a determined OpenLineage user cover this by writing one
more integration? If yes, it is a configuration gap and it does not belong in this suite.
Ship fewer, stronger cases.
