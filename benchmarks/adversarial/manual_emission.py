"""What OpenLineage needs from a plain script: lineage the author DECLARES. P5.

This is the manual-emission path openlineage-python offers for code no
integration covers. It is dark_zone's producer (`nightly_enrich.py`: read
`orders`, produce to `enriched_orders`) written out by hand: the author names
the job, invents a run id, and lists every input and output dataset in
OpenLineage's naming, then emits START and COMPLETE. Nothing checks that the
declared datasets are the ones the code actually touched. DCP attests them from
the queries and the records it sees instead.

benchmarks/adversarial/baseline_check.py runs this file as its positive
control: it must deliver exactly two events to the stub, which shows that the
stub and OPENLINEAGE_URL would have caught anything the uninstrumented scripts
emitted.
"""

import uuid
from datetime import datetime, timezone

from openlineage.client import OpenLineageClient
from openlineage.client.event_v2 import (
    InputDataset,
    Job,
    OutputDataset,
    Run,
    RunEvent,
    RunState,
)

PRODUCER = "https://github.com/dev1702ed/Wiretap/tree/main/benchmarks/adversarial"


def emit(client, state, run_id):
    client.emit(
        RunEvent(
            eventType=state,
            eventTime=datetime.now(timezone.utc).isoformat(),
            run=Run(runId=run_id),
            job=Job(namespace="manual", name="nightly_enrich.py"),
            # Every dataset is typed in by the author:
            inputs=[InputDataset("postgres://localhost:5432", "dcp.public.orders")],
            outputs=[OutputDataset("kafka://localhost:9092", "enriched_orders")],
            producer=PRODUCER,
        )
    )


if __name__ == "__main__":
    client = OpenLineageClient()  # transport from OPENLINEAGE_URL
    run_id = str(uuid.uuid4())
    emit(client, RunState.START, run_id)
    emit(client, RunState.COMPLETE, run_id)
