# P5.1: the optimisations, CPU microbenchmark on Python 3.11 and 3.13, before (`p51-before-cpu-extra`) and after (`p51-after-cpu-extra`)

Rendered by `benchmarks/render.py --compare` from the two runs' results JSON. Do not edit by hand.

|  | Before | After |
|---|---|---|
| Git commit | `9cf6e7d700f9495a7f5a5e45de113bef1d691194` | `f7125a70163d38e1db18b3b6782eaa660fcb633e` |
| Command | `python benchmarks/run.py --label p51-before-cpu-extra --only cpu --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.11/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.13/bin/python` | `python benchmarks/run.py --label p51-after-cpu-extra --only cpu --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.11/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.13/bin/python` |
| Started (UTC) | 2026-10-03T20:46:30+00:00 | 2026-10-03T20:49:12+00:00 |

### 4a, Python 3.11.15: `_capture` (µs)

| Tier | p50 before | p50 after | p99 before | p99 after |
|---|---|---|---|---|
| T1 point read | 9.8 | 9.6 | 34.0 | 37.4 |
| T2 join | 16.6 | 16.7 | 45.0 | 53.9 |
| T3 insert values | 9.1 | 9.3 | 35.3 | 37.1 |
| T4 insert-select | 15.9 | 15.9 | 47.3 | 53.3 |
| T5 analytical | 16.6 | 17.6 | 48.4 | 72.6 |
| L1 point read, literal (added in P5.1) | 223.0 | 14.6 | 535.2 | 49.8 |
| L3 insert values, literal (added in P5.1) | 166.0 | 15.1 | 333.0 | 48.9 |
| L5 analytical, literal (added in P5.1) | 2353.0 | 86.0 | 5591.8 | 149.9 |

### 4a, Python 3.13.14: `_capture` (µs)

| Tier | p50 before | p50 after | p99 before | p99 after |
|---|---|---|---|---|
| T1 point read | 9.4 | 9.2 | 35.9 | 36.3 |
| T2 join | 16.8 | 16.6 | 64.4 | 47.2 |
| T3 insert values | 8.8 | 8.8 | 42.6 | 32.6 |
| T4 insert-select | 26.3 | 15.9 | 71.5 | 53.4 |
| T5 analytical | 22.5 | 16.6 | 71.2 | 46.1 |
| L1 point read, literal (added in P5.1) | 217.5 | 14.8 | 635.7 | 54.2 |
| L3 insert values, literal (added in P5.1) | 174.1 | 17.9 | 615.8 | 68.9 |
| L5 analytical, literal (added in P5.1) | 2438.6 | 89.4 | 4783.4 | 173.4 |
