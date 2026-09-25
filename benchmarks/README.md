# Benchmarks — the product

Everything else in this repo is apparatus. These three artifacts are what the work
actually produces.

## The bar

| | |
|---|---|
| **Genuine finding** | DCP recovers ≥1 real, useful lineage edge that OpenLineage structurally cannot, at < 1 ms p99 overhead |
| **Just a demo** | DCP re-derives edges OpenLineage already had |

Write results against this bar honestly. A result that lands in the "demo" column is still
a result — it narrows the claim, which is more useful than overstating it.

## 1. `ground_truth/`

A known data flow with a hand-written expected lineage graph. Measures precision and
recall on edge and node recovery.

Target: 100% on covered protocols — this is deterministic capture, not inference, so
anything below 100% is a bug, not a limitation.

## 2. `adversarial/` — the money shot

≥3 data movements that application-layer instrumentation **provably** misses. The headline
case is an ad-hoc script with no framework plugin.

**Write these first, at P0, as failing tests.** Building capture first and retrofitting a
proof at the end is how three-week sprints produce demos instead of findings.

For each case, record:
- What the movement is, and why no application-layer tool sees it
- OpenLineage's graph (the edge is absent)
- DCP's graph (the edge is present)
- Whether the miss is *structural* or merely *unconfigured* — this distinction is the
  entire credibility of the claim, and the place a reviewer will push hardest

**Be ruthless about the second bullet.** An edge OpenLineage misses because nobody
installed the plugin is a configuration gap. An edge it misses because there is no plugin
that could exist for an ad-hoc script is a structural gap. Only the second kind counts.

## 3. `overhead/`

p50/p99 added latency per intercepted call, and throughput delta.

Target: < 1 ms p99, < 2% throughput. Achievable because DCP reads the control path (query
text, headers) and emits async — it never touches result payloads.

Measure with the emitter under realistic backpressure, not an idle sink. An overhead number
from an unloaded console emitter is not a real number.
