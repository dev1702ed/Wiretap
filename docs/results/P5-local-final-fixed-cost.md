# Fixed cost per call: `local-final`

Rendered by `benchmarks/render.py --fixed-cost` from the run's results JSON. Do not edit by hand.

|  |  |
|---|---|
| Label | `local-final` |
| Command | `python benchmarks/run.py --label local-final` |
| Started (UTC) | 2026-10-06T14:54:47+00:00 |
| Git commit | `9e7b704cf09e625c7cd362970ab9263c067d5086` |
| Working tree dirty | False |
| OS | Windows-11-10.0.26200-SP0 |
| CPU | Intel(R) Core(TM) i7-14650HX, 24 logical cores |

### The fixed cost per call and the < 2% throughput target

From the run's implied added µs per call (point estimate). A fixed cost c per call takes c / (q + c) of the throughput of a query whose own latency is q, so the loss is under 2% once q > 49 × c. The last columns apply each cost to representative query latencies.

| Tier | Config | Implied µs/call [95% CI] | Loss < 2% for queries slower than (µs) | Loss at a 1 ms query | Loss at a 10 ms query | Loss at a 100 ms query |
|---|---|---|---|---|---|---|
| T1 point read | file | +72.2 [+69.1, +75.3] | 3536.1 | 6.73% | 0.72% | 0.07% |
| T1 point read | http | +55.4 [+52.7, +57.7] | 2716.9 | 5.25% | 0.55% | 0.06% |
| T1 point read | http-down | +34.9 [+31.2, +38.4] | 1708.7 | 3.37% | 0.35% | 0.03% |
| T1 point read | file+sqlcomment | +96.3 [+93.2, +99.5] | 4717.6 | 8.78% | 0.95% | 0.10% |
| T2 join | file | +96.7 [+93.5, +99.5] | 4736.3 | 8.81% | 0.96% | 0.10% |
| T2 join | http | +66.2 [+63.2, +69.2] | 3246.0 | 6.21% | 0.66% | 0.07% |
| T2 join | http-down | +53.5 [+50.5, +57.3] | 2621.3 | 5.08% | 0.53% | 0.05% |
| T2 join | file+sqlcomment | +117.9 [+113.7, +122.4] | 5778.0 | 10.55% | 1.17% | 0.12% |
| T3 insert values | file | +63.6 [+46.1, +80.2] | 3115.3 | 5.98% | 0.63% | 0.06% |
| T3 insert values | http | +177.4 [+123.4, +230.6] | 8691.7 | 15.07% | 1.74% | 0.18% |
| T3 insert values | http-down | +63.9 [+27.5, +100.4] | 3129.3 | 6.00% | 0.63% | 0.06% |
| T3 insert values | file+sqlcomment | +91.3 [+42.0, +142.6] | 4475.2 | 8.37% | 0.91% | 0.09% |
| T4 insert-select | file | +80.9 [+42.7, +117.5] | 3966.0 | 7.49% | 0.80% | 0.08% |
| T4 insert-select | http | +301.6 [+238.8, +365.2] | 14779.1 | 23.17% | 2.93% | 0.30% |
| T4 insert-select | http-down | +93.5 [+61.5, +123.9] | 4580.2 | 8.55% | 0.93% | 0.09% |
| T4 insert-select | file+sqlcomment | +85.7 [+39.4, +136.1] | 4198.4 | 7.89% | 0.85% | 0.09% |
| T5 analytical | file | +96.0 [+92.1, +100.1] | 4703.3 | 8.76% | 0.95% | 0.10% |
| T5 analytical | http | +61.6 [+54.7, +67.7] | 3016.2 | 5.80% | 0.61% | 0.06% |
| T5 analytical | http-down | +45.6 [+42.6, +49.0] | 2235.6 | 4.36% | 0.45% | 0.05% |
| T5 analytical | file+sqlcomment | +113.5 [+108.4, +118.7] | 5560.4 | 10.19% | 1.12% | 0.11% |
| L1 point read, literal (added in P5.1) | file | +83.4 [+79.3, +87.2] | 4087.3 | 7.70% | 0.83% | 0.08% |
| L1 point read, literal (added in P5.1) | http | +70.2 [+65.2, +74.5] | 3441.6 | 6.56% | 0.70% | 0.07% |
| L1 point read, literal (added in P5.1) | http-down | +53.4 [+48.6, +57.7] | 2616.5 | 5.07% | 0.53% | 0.05% |
| L1 point read, literal (added in P5.1) | file+sqlcomment | +96.0 [+92.4, +100.1] | 4706.2 | 8.76% | 0.95% | 0.10% |
| L3 insert values, literal (added in P5.1) | file | +81.0 [+41.8, +120.4] | 3969.2 | 7.49% | 0.80% | 0.08% |
| L3 insert values, literal (added in P5.1) | http | +325.4 [+265.4, +383.4] | 15945.4 | 24.55% | 3.15% | 0.32% |
| L3 insert values, literal (added in P5.1) | http-down | +43.2 [+4.7, +82.9] | 2117.2 | 4.14% | 0.43% | 0.04% |
| L3 insert values, literal (added in P5.1) | file+sqlcomment | +98.0 [+34.1, +164.7] | 4803.4 | 8.93% | 0.97% | 0.10% |
| L5 analytical, literal (added in P5.1) | file | +177.1 [+132.9, +213.4] | 8678.2 | 15.05% | 1.74% | 0.18% |
| L5 analytical, literal (added in P5.1) | http | +130.1 [+98.5, +158.6] | 6377.1 | 11.52% | 1.28% | 0.13% |
| L5 analytical, literal (added in P5.1) | http-down | +119.0 [+80.9, +150.1] | 5830.9 | 10.63% | 1.18% | 0.12% |
| L5 analytical, literal (added in P5.1) | file+sqlcomment | +191.7 [+144.4, +229.9] | 9393.2 | 16.09% | 1.88% | 0.19% |
| Kafka `produce()` | file | +3.9 [+0.6, +7.1] | 190.0 | 0.39% | 0.04% | 0.00% |
| Kafka `produce()` | http | -0.7 [-4.5, +3.1] | any | -0.07% | -0.01% | -0.00% |
