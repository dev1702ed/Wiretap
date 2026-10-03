# P5 Stage 5: parse cache, before (`fixture`) and after (`fixture-after`)

Rendered by `benchmarks/render.py --compare` from the two runs' results JSON. Do not edit by hand.

|  | Before | After |
|---|---|---|
| Git commit | `0000000000000000000000000000000000000000` | `0000000000000000000000000000000000000000` |
| Command | `python benchmarks/run.py --label fixture --quick (synthetic test fixture)` | `python benchmarks/run.py --label fixture --quick (synthetic test fixture)` |
| Started (UTC) | 2026-01-01T00:00:00+00:00 | 2026-01-01T00:00:00+00:00 |

### 4a, Python 3.12.3: `_capture` (µs)

| Tier | p50 before | p50 after | p99 before | p99 after |
|---|---|---|---|---|
| T1 point read | 297.7 | 148.8 | 526.3 | 263.1 |
| T5 analytical | 2823.1 | 1411.5 | 5465.7 | 2732.9 |

### 4b, T1 point read

| Config | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict |
|---|---|---|---|---|---|---|
| file | +1246.4 [+739.5, +1753.3] | +1246.4 [+739.5, +1753.3] | inconclusive → inconclusive | -79.83% [-80.70, -78.96] | -79.83% [-80.70, -78.96] | not met → not met |
| http | +1190.4 [+980.0, +1388.5] | +1190.4 [+980.0, +1388.5] | inconclusive → inconclusive | -81.59% [-82.68, -80.61] | -81.59% [-82.68, -80.61] | not met → not met |
| http-down | +1085.2 [+811.8, +1372.1] | +1085.2 [+811.8, +1372.1] | inconclusive → inconclusive | -79.69% [-80.03, -79.37] | -79.69% [-80.03, -79.37] | not met → not met |
| file+sqlcomment | +934.3 [+643.3, +1255.3] | +934.3 [+643.3, +1255.3] | inconclusive → inconclusive | -80.55% [-81.89, -79.21] | -80.55% [-81.89, -79.21] | not met → not met |
