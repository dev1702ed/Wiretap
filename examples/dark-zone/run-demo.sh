#!/usr/bin/env bash
# The demo service's entrypoint. Runs once and exits.
set -euo pipefail
cd /demo

echo "== waiting for Postgres, Kafka and Marquez"
python wait_for.py

echo "== seeding (no DCP: set-up is not lineage)"
python seed.py

rm -f /demo/dcp_events.jsonl
export DCP_EMIT=file:///demo/dcp_events.jsonl

echo "== nightly_enrich.py under dcp-instrument (the script has no DCP code)"
dcp-instrument python nightly_enrich.py

echo "== warehouse_loader.py under dcp-instrument"
dcp-instrument python warehouse_loader.py

echo "== DCP events recorded: $(wc -l < /demo/dcp_events.jsonl)"
echo "== posting to Marquez with the OpenLineage bridge"
python -m dcp_openlineage --events /demo/dcp_events.jsonl --post "${MARQUEZ_URL}"

echo "== done: open http://localhost:3000 and pick the namespace dcp://dark-zone-demo"
