# P5 Stage 5: parse cache, before (`sandbox-before-cache`) and after (`sandbox`)

Rendered by `benchmarks/render.py --compare` from the two runs' results JSON. Do not edit by hand.

|  | Before | After |
|---|---|---|
| Git commit | `11d79942fbe3951942762fe4ccf861bde63450a8` | `9ff493f284a0ba5443ef0aa62719176be33106a4` |
| Command | `python benchmarks/run.py --label sandbox-before-cache --only cpu,overhead --cpu-python /tmp/claude-0/-home-user-Wiretap/233c9775-cfe2-56ba-8a8a-6fe3b5f17f33/scratchpad/p5-3.10.20/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/233c9775-cfe2-56ba-8a8a-6fe3b5f17f33/scratchpad/p5/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/233c9775-cfe2-56ba-8a8a-6fe3b5f17f33/scratchpad/p5-3.14.8/bin/python` | `python benchmarks/run.py --label sandbox --cpu-python /tmp/claude-0/-home-user-Wiretap/233c9775-cfe2-56ba-8a8a-6fe3b5f17f33/scratchpad/p5-3.10.20/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/233c9775-cfe2-56ba-8a8a-6fe3b5f17f33/scratchpad/p5/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/233c9775-cfe2-56ba-8a8a-6fe3b5f17f33/scratchpad/p5-3.14.8/bin/python` |
| Started (UTC) | 2026-10-03T09:48:30+00:00 | 2026-10-03T10:22:08+00:00 |

### 4a, Python 3.10.20: `_capture` (µs)

| Tier | p50 before | p50 after | p99 before | p99 after |
|---|---|---|---|---|
| T1 point read | 408.8 | 12.9 | 964.3 | 44.6 |
| T2 join | 791.6 | 22.3 | 1699.8 | 68.3 |
| T3 insert values | 337.0 | 12.1 | 667.9 | 44.1 |
| T4 insert-select | 533.3 | 21.2 | 1181.8 | 92.5 |
| T5 analytical | 3938.1 | 22.4 | 9072.7 | 59.1 |

### 4a, Python 3.12.3: `_capture` (µs)

| Tier | p50 before | p50 after | p99 before | p99 after |
|---|---|---|---|---|
| T1 point read | 287.8 | 11.6 | 515.1 | 45.3 |
| T2 join | 583.4 | 20.8 | 1198.5 | 62.4 |
| T3 insert values | 240.3 | 10.8 | 535.2 | 42.1 |
| T4 insert-select | 400.8 | 21.1 | 938.8 | 88.6 |
| T5 analytical | 2851.2 | 20.8 | 6157.0 | 65.7 |

### 4a, Python 3.14.8: `_capture` (µs)

| Tier | p50 before | p50 after | p99 before | p99 after |
|---|---|---|---|---|
| T1 point read | 289.8 | 8.8 | 845.9 | 42.6 |
| T2 join | 547.1 | 15.7 | 1343.8 | 53.5 |
| T3 insert values | 217.2 | 8.1 | 566.0 | 28.9 |
| T4 insert-select | 377.5 | 15.0 | 1101.8 | 60.4 |
| T5 analytical | 2721.2 | 15.5 | 6194.8 | 44.2 |

### 4b, T1 point read

| Config | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict |
|---|---|---|---|---|---|---|
| file | +1204.9 [+966.9, +1529.2] | +158.5 [+117.4, +203.4] | inconclusive → met | -79.57% [-80.37, -78.65] | -38.94% [-41.72, -36.07] | not met → not met |
| http | +1373.3 [+1199.0, +1534.2] | +715.7 [+677.3, +759.4] | not met → met | -80.91% [-81.77, -80.09] | -41.25% [-44.30, -38.01] | not met → not met |
| http-down | +986.7 [+829.0, +1194.4] | +176.9 [+99.8, +261.7] | inconclusive → met | -78.56% [-79.49, -77.54] | -32.74% [-34.78, -30.72] | not met → not met |
| file+sqlcomment | +1046.4 [+943.3, +1167.0] | +213.1 [+158.8, +266.9] | inconclusive → met | -80.12% [-81.15, -79.07] | -47.01% [-50.27, -43.87] | not met → not met |

### 4b, T2 join

| Config | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict |
|---|---|---|---|---|---|---|
| file | +1571.1 [+1416.5, +1721.5] | +252.2 [+172.1, +353.2] | not met → met | -85.40% [-85.98, -84.79] | -46.21% [-49.40, -43.22] | not met → not met |
| http | +2096.4 [+1873.2, +2316.1] | +375.8 [+278.6, +479.2] | not met → met | -86.70% [-87.17, -86.15] | -43.41% [-45.94, -40.34] | not met → not met |
| http-down | +1518.2 [+1362.8, +1671.1] | +174.9 [+102.8, +251.7] | not met → met | -85.25% [-85.80, -84.65] | -40.32% [-43.56, -37.29] | not met → not met |
| file+sqlcomment | +1711.7 [+1514.9, +1921.0] | +302.0 [+245.4, +365.8] | not met → met | -85.99% [-86.56, -85.45] | -52.47% [-54.92, -50.06] | not met → not met |

### 4b, T3 insert values

| Config | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict |
|---|---|---|---|---|---|---|
| file | +996.4 [+677.2, +1296.3] | +234.1 [+89.1, +379.0] | inconclusive → met | -53.05% [-56.44, -49.72] | -21.35% [-27.68, -15.14] | not met → not met |
| http | +1355.5 [+979.1, +1765.8] | +685.3 [+457.2, +902.8] | inconclusive → met | -56.78% [-59.74, -53.80] | -24.85% [-30.44, -18.83] | not met → not met |
| http-down | +844.1 [+529.8, +1170.4] | +590.9 [+274.3, +966.2] | inconclusive → met | -51.81% [-55.89, -47.15] | -18.56% [-27.51, -10.34] | not met → not met |
| file+sqlcomment | +1156.2 [+779.0, +1506.0] | +520.8 [+192.9, +878.9] | inconclusive → met | -55.09% [-58.67, -51.47] | -25.75% [-34.50, -17.61] | not met → not met |

### 4b, T4 insert-select

| Config | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict |
|---|---|---|---|---|---|---|
| file | +1452.6 [+951.4, +1934.3] | +425.4 [+307.6, +541.3] | inconclusive → met | -62.22% [-64.92, -59.42] | -27.08% [-29.56, -24.32] | not met → not met |
| http | +1426.8 [+1201.0, +1635.3] | +730.3 [+558.9, +912.0] | not met → met | -62.99% [-65.39, -60.54] | -27.80% [-33.36, -20.45] | not met → not met |
| http-down | +1463.9 [+1087.9, +1807.2] | +476.7 [+316.6, +658.8] | not met → met | -61.09% [-63.91, -58.22] | -23.21% [-29.93, -15.21] | not met → not met |
| file+sqlcomment | +1680.3 [+1172.2, +2163.8] | +596.5 [+344.8, +858.8] | not met → met | -63.51% [-65.75, -61.15] | -29.37% [-34.45, -22.50] | not met → not met |

### 4b, T5 analytical

| Config | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict |
|---|---|---|---|---|---|---|
| file | +7294.7 [+6887.3, +7724.3] | +304.1 [+229.6, +393.0] | not met → met | -94.14% [-94.47, -93.67] | -39.71% [-42.88, -36.50] | not met → not met |
| http | +7917.1 [+7347.8, +8554.6] | +1121.9 [+868.4, +1350.3] | not met → inconclusive | -94.42% [-94.74, -94.01] | -40.18% [-44.33, -35.60] | not met → not met |
| http-down | +7390.3 [+6951.4, +7858.2] | +275.2 [+210.4, +346.6] | not met → met | -94.25% [-94.57, -93.93] | -33.23% [-37.21, -28.99] | not met → not met |
| file+sqlcomment | +7921.6 [+7569.9, +8254.5] | +380.7 [+279.3, +496.5] | not met → met | -94.31% [-94.64, -93.87] | -47.25% [-50.14, -44.45] | not met → not met |
