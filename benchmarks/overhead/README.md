# Overhead protocol

## Method

1. Baseline: N operations, uninstrumented.
2. Instrumented: same N, DCP active, emitter under realistic backpressure.
3. Report p50/p99 added latency per call and throughput delta.

Run both in the same process and the same session; alternate to cancel drift.

## Targets

- < 1 ms p99 added latency
- < 2% throughput impact

## Do not

- Measure against an idle console emitter and call it production overhead.
- Report a mean. The p99 is the number that decides whether anyone deploys this.
