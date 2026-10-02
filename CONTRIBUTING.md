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
pip install -e "./sdk-python[dev]" -e "./backend[dev]"
ruff check sdk-python backend benchmarks bridges
ruff format --check sdk-python backend benchmarks bridges
pytest sdk-python/tests
pytest backend/tests
```

CI runs these on Python 3.10, 3.12 and 3.14 (`.github/workflows/ci.yml`).

## Style

`ruff` for lint and format. Run before pushing; CI enforces.
