# dcp — the DCP capture SDK

Transport-layer data lineage for Python: DCP captures lineage inside the Postgres
(psycopg 3) and Kafka (confluent-kafka) client libraries, where data physically moves,
instead of from what applications report.

No code changes: run a script under `dcp-instrument`. On PyPI this package is named
`wiretap-dcp`; the import name is `dcp` (the PyPI name `dcp` belongs to an unrelated
project, so do not install both in one environment). On Linux or macOS (bash):

```bash
pip install "wiretap-dcp[postgres,kafka]"
DCP_EMIT=file://dcp_events.jsonl dcp-instrument python my_script.py
```

The event format, the benchmarks and the measured results are in the project
repository: https://github.com/dev1702ed/Wiretap (start with its README, then
`docs/results/V1.md`). Licensed under Apache 2.0.
