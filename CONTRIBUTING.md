# Contributing

## Ground rules

1. **The spec is the contract.** Any change to emitted events must update
   `spec/envelope.schema.json` in the same PR. CI fails otherwise.
2. **No claim without a number.** Performance or coverage claims in docs must trace to a
   reproducible benchmark in `/benchmarks`.
3. **Monitor-only.** v1 does not block, drop, or modify traffic. PRs adding inline
   enforcement will be declined for v1 scope.

## Good first issues

- A new DBAPI driver interceptor — self-contained, follows `interceptors/postgres.py`
- A new emitter sink — implement `emitters/base.py`
- Additional adversarial cases in `benchmarks/adversarial/`

## Dev setup

```bash
cd sdk-python && pip install -e ".[dev]"
pytest
```

## Style

`ruff` for lint and format. Run before pushing; CI enforces.
