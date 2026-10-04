# Contributing

## Ground rules

1. **The spec is the contract.** Any change to emitted events must update
   `spec/envelope.schema.json` in the same PR. CI fails otherwise.
2. **No claim without a number.** Performance or coverage claims in docs must trace to a
   reproducible benchmark in `/benchmarks`.
3. **Monitor-only.** v1 never blocks or drops traffic and never alters query semantics.
   Its one modification, a trace comment on outbound SQL, is opt-in via
   `dcp.init(propagate_sql=True)` and tested not to change results. PRs adding inline
   enforcement will be declined for v1 scope.

## Good first issues

- A new DBAPI driver interceptor — self-contained, follows `interceptors/postgres.py`
- A new emitter sink — implement `emitters/base.py`
- Additional adversarial cases in `benchmarks/adversarial/`

## Dev setup

From the repository root, install every package the way CI does, then run
every CI step:

```bash
pip install -e "./sdk-python[dev]" -e "./backend[dev]" -e "./bridges/openlineage[dev]"
ruff check sdk-python backend benchmarks bridges
ruff format --check sdk-python backend benchmarks bridges
pytest sdk-python/tests
pytest backend/tests
pytest bridges/openlineage/tests
pytest benchmarks/tests
```

CI runs these on Python 3.10, 3.12 and 3.14 (`.github/workflows/ci.yml`), and the
four test suites on Windows with Python 3.14 (the `windows` job).

## Running the benchmarks

Every published number comes from one command, which writes raw JSON to
`benchmarks/results/<label>/` (gitignored) and renders
`docs/results/P5-<label>.md`:

```bash
# The pinned benchmark environment (P5.1): one pip command, so the constraints
# apply to the three packages too
pip install -c benchmarks/constraints.txt -e "./sdk-python[dev]" -e "./backend[dev]" -e "./bridges/openlineage[dev]" -r benchmarks/requirements.txt
python -m ipykernel install --user --name python3   # once, for the notebook workload
python benchmarks/run.py --label local              # full mode
python benchmarks/run.py --label local --quick      # 5 x 300 instead of 10 x 2,000
python benchmarks/run.py --label local --only replay,cpu   # no services needed
```

The `live`, `adversarial` and `overhead` stages need PostgreSQL on
`localhost:5432` (database `dcp`, user `postgres`, password from
`DCP_PG_PASSWORD`, default `dcp`) and Kafka on `localhost:9092`; without them
they are skipped, with the reason. **They drop and re-create the benchmark
tables in database `dcp` and the `enriched_orders` and `overhead_bench`
topics.** `benchmarks/requirements.txt` and `benchmarks/constraints.txt` pin every
version that affects measurement; `run.py` compares the installed versions
with them and records any mismatch in the result's environment table (a
warning, not a failure). `--cpu-python PATH` (repeatable) runs the CPU microbenchmark under
other interpreters too; each needs the SDK installed. Never edit a generated
results file by hand: re-run the command. The CI `live` job runs
`--label ci --quick` on every PR and publishes the result as its job summary.

## Style

`ruff` for lint and format. Run before pushing; CI enforces.
