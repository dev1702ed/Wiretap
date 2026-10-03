"""4b worker: times confluent-kafka produce() calls. Plain: no DCP code. P5.

    python kafka_worker.py OUT.json WARMUP MESSAGES      (configuration `base`)
    dcp-instrument python kafka_worker.py OUT.json ...   (`file`, `http`)

WARMUP messages are produced and flushed, then MESSAGES 1 KB messages, each
produce() call timed with time.perf_counter_ns, then one flush(). Throughput
is MESSAGES over the wall time of the produce loop plus the flush.
"""

import json
import sys
import time

from confluent_kafka import Producer
from queries import KAFKA_BOOTSTRAP, KAFKA_MESSAGE_BYTES, KAFKA_TOPIC


def main(argv: list[str]) -> int:
    out, warmup, messages = argv[0], int(argv[1]), int(argv[2])
    payload = b"x" * KAFKA_MESSAGE_BYTES
    producer = Producer({"bootstrap.servers": KAFKA_BOOTSTRAP})
    for _ in range(warmup):
        producer.produce(KAFKA_TOPIC, payload)
    if producer.flush(60) != 0:
        raise SystemExit("warm-up messages were not delivered")
    clock = time.perf_counter_ns
    samples = []
    started = clock()
    for _ in range(messages):
        t0 = clock()
        producer.produce(KAFKA_TOPIC, payload)
        samples.append(clock() - t0)
    flush_started = clock()
    undelivered = producer.flush(120)
    finished = clock()
    if undelivered:
        raise SystemExit(f"{undelivered} messages were not delivered")
    result = {
        "ns": samples,
        "elapsed_ns": finished - started,
        "flush_ns": finished - flush_started,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
