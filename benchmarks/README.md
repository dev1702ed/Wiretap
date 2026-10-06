# Benchmarks — the product

Everything else in this repo is apparatus. These three artifacts are what the work
actually produces.

**Every number comes from one command** (P5; it runs the same in PowerShell):

```bash
python benchmarks/run.py --label <label> [--quick] [--only replay,live,adversarial,scale,overhead,cpu]
```

It runs whatever stages the environment supports (the ground-truth replay, the live
harness, the adversarial suite, the generated keys at scale (P5.1), live overhead, the CPU
microbenchmark), skips the rest
with a stated reason, writes raw JSON to `benchmarks/results/<label>/` (gitignored) and
renders `docs/results/P5-<label>.md` with `render.py`, the only code that writes numbers
into markdown. See `CONTRIBUTING.md` for set-up, `live/README.md` for the live harness,
`adversarial/BASELINE.md` for the OpenLineage baseline, and `overhead/README.md` for the
overhead method.

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
anything below 100% is a bug, not a limitation. In v1 this holds on the hand-written keys.
On the generated keys, every extra item DCP reports is a distractor read (job-level
parenting over-approximates by design), and on the stress set every miss is one of DCP's
two named failure modes; both are checked by code, and anything unexplained counts as a
bug ([`LIMITATIONS.md`, §1](../docs/LIMITATIONS.md#1-capture-what-dcps-events-cannot-say)).

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

Target: < 1 ms p99, < 2% throughput. DCP reads the control path (query text, headers) and
never touches result payloads. In v1 the p99 target is met and the throughput target is
not: against sub-millisecond queries the fixed cost per call is more than 2%
([`V1.md`](../docs/results/V1.md#the-definition-of-done-final)).

Measure with the emitter under realistic backpressure, not an idle sink. An overhead number
from an unloaded console emitter is not a real number. The method, configurations and
statistics are in [`overhead/README.md`](overhead/README.md).
