# Fixed cost per call: `local-final`

Rendered by `benchmarks/render.py --fixed-cost` from the run's results JSON. Do not edit by hand.

|  |  |
|---|---|
| Label | `local-final` |
| Command | `python benchmarks/run.py --label local-final` |
| Started (UTC) | 2026-10-05T17:09:06+00:00 |
| Git commit | `fe54bc5b2d861c09019959c4ae40d218515642cf` |
| Working tree dirty | False |
| OS | Windows-11-10.0.26200-SP0 |
| CPU | Intel(R) Core(TM) i7-14650HX, 24 logical cores |

### The fixed cost per call and the < 2% throughput target

From the run's implied added µs per call (point estimate). A fixed cost c per call takes c / (q + c) of the throughput of a query whose own latency is q, so the loss is under 2% once q > 49 × c. The last columns apply each cost to representative query latencies.

| Tier | Config | Implied µs/call [95% CI] | Loss < 2% for queries slower than (µs) | Loss at a 1 ms query | Loss at a 10 ms query | Loss at a 100 ms query |
|---|---|---|---|---|---|---|
| T1 point read | file | +68.9 [+63.6, +73.9] | 3374.0 | 6.44% | 0.68% | 0.07% |
| T1 point read | http | +47.7 [+40.9, +53.0] | 2338.4 | 4.55% | 0.47% | 0.05% |
| T1 point read | http-down | +57.5 [+39.9, +77.7] | 2815.2 | 5.43% | 0.57% | 0.06% |
| T1 point read | file+sqlcomment | +94.5 [+85.3, +103.0] | 4630.4 | 8.63% | 0.94% | 0.09% |
| T2 join | file | +94.8 [+87.0, +102.3] | 4646.8 | 8.66% | 0.94% | 0.09% |
| T2 join | http | +55.6 [+46.0, +65.0] | 2724.0 | 5.27% | 0.55% | 0.06% |
| T2 join | http-down | +54.8 [+43.6, +68.1] | 2686.1 | 5.20% | 0.55% | 0.05% |
| T2 join | file+sqlcomment | +112.8 [+103.3, +122.3] | 5526.5 | 10.14% | 1.12% | 0.11% |
| T3 insert values | file | +77.4 [+57.2, +95.1] | 3790.2 | 7.18% | 0.77% | 0.08% |
| T3 insert values | http | +328.1 [+191.6, +530.2] | 16074.9 | 24.70% | 3.18% | 0.33% |
| T3 insert values | http-down | +99.6 [+29.7, +190.0] | 4882.3 | 9.06% | 0.99% | 0.10% |
| T3 insert values | file+sqlcomment | +82.2 [+29.7, +139.1] | 4027.7 | 7.60% | 0.82% | 0.08% |
| T4 insert-select | file | +112.8 [+87.3, +141.6] | 5528.6 | 10.14% | 1.12% | 0.11% |
| T4 insert-select | http | +274.3 [+206.7, +341.8] | 13442.6 | 21.53% | 2.67% | 0.27% |
| T4 insert-select | http-down | +132.8 [+78.7, +186.3] | 6505.9 | 11.72% | 1.31% | 0.13% |
| T4 insert-select | file+sqlcomment | +161.2 [+123.4, +197.5] | 7898.9 | 13.88% | 1.59% | 0.16% |
| T5 analytical | file | +110.1 [+95.5, +127.5] | 5396.1 | 9.92% | 1.09% | 0.11% |
| T5 analytical | http | +132.5 [+58.9, +258.0] | 6493.2 | 11.70% | 1.31% | 0.13% |
| T5 analytical | http-down | +60.6 [+52.7, +68.7] | 2970.7 | 5.72% | 0.60% | 0.06% |
| T5 analytical | file+sqlcomment | +135.1 [+118.9, +155.4] | 6620.9 | 11.90% | 1.33% | 0.13% |
| L1 point read, literal (added in P5.1) | file | +93.9 [+79.3, +111.4] | 4602.9 | 8.59% | 0.93% | 0.09% |
| L1 point read, literal (added in P5.1) | http | +135.8 [+69.3, +234.4] | 6654.7 | 11.96% | 1.34% | 0.14% |
| L1 point read, literal (added in P5.1) | http-down | +58.2 [+48.6, +68.4] | 2852.1 | 5.50% | 0.58% | 0.06% |
| L1 point read, literal (added in P5.1) | file+sqlcomment | +114.3 [+100.6, +129.4] | 5598.4 | 10.25% | 1.13% | 0.11% |
| L3 insert values, literal (added in P5.1) | file | +149.6 [+107.0, +195.3] | 7332.4 | 13.02% | 1.47% | 0.15% |
| L3 insert values, literal (added in P5.1) | http | +461.4 [+234.7, +776.4] | 22609.2 | 31.57% | 4.41% | 0.46% |
| L3 insert values, literal (added in P5.1) | http-down | +72.1 [+12.5, +132.2] | 3530.9 | 6.72% | 0.72% | 0.07% |
| L3 insert values, literal (added in P5.1) | file+sqlcomment | +138.2 [+71.5, +210.0] | 6771.7 | 12.14% | 1.36% | 0.14% |
| L5 analytical, literal (added in P5.1) | file | +172.2 [+160.6, +182.7] | 8437.6 | 14.69% | 1.69% | 0.17% |
| L5 analytical, literal (added in P5.1) | http | +183.0 [+131.8, +250.4] | 8965.8 | 15.47% | 1.80% | 0.18% |
| L5 analytical, literal (added in P5.1) | http-down | +126.8 [+104.7, +149.0] | 6211.1 | 11.25% | 1.25% | 0.13% |
| L5 analytical, literal (added in P5.1) | file+sqlcomment | +194.1 [+171.6, +219.1] | 9512.7 | 16.26% | 1.90% | 0.19% |
| Kafka `produce()` | file | +4.5 [+1.8, +7.1] | 219.0 | 0.44% | 0.04% | 0.00% |
| Kafka `produce()` | http | +0.2 [-3.0, +3.6] | 10.5 | 0.02% | 0.00% | 0.00% |
