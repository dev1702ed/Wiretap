# P5.1: the final code (O1, O2, O3 revised, A5), before (`p51-before-final`) and after (`p51-after-final`)

Rendered by `benchmarks/render.py --compare` from the two runs' results JSON. Do not edit by hand.

|  | Before | After |
|---|---|---|
| Git commit | `9cf6e7d700f9495a7f5a5e45de113bef1d691194` | `c645a15d8dfe79744a0291fcc88224aded138722` |
| Command | `python benchmarks/run.py --label p51-before-final --only cpu,overhead --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.10/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.11/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.12/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.13/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.14/bin/python` | `python benchmarks/run.py --label p51-after-final --only cpu,overhead --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.10/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.11/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.12/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.13/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.14/bin/python` |
| Started (UTC) | 2026-10-03T20:59:03+00:00 | 2026-10-03T21:23:51+00:00 |

### 4a, Python 3.10.20: `_capture` and `_classify` (µs)

| Tier | capture p50 before | after | capture p99 before | after | classify p50 before | after |
|---|---|---|---|---|---|---|
| T1 point read | 10.6 | 10.3 | 38.9 | 37.1 | 0.9 | 0.9 |
| T2 join | 18.1 | 17.7 | 53.5 | 51.1 | 1.4 | 1.3 |
| T3 insert values | 9.9 | 9.8 | 33.8 | 33.2 | 0.9 | 0.9 |
| T4 insert-select | 17.6 | 17.0 | 62.4 | 46.5 | 2.5 | 1.4 |
| T5 analytical | 18.1 | 17.8 | 67.5 | 80.5 | 1.4 | 1.4 |
| L1 point read, literal (added in P5.1) | 267.6 | 19.1 | 540.6 | 76.0 | 247.4 | 5.0 |
| L3 insert values, literal (added in P5.1) | 210.8 | 17.7 | 398.0 | 68.7 | 189.2 | 6.1 |
| L5 analytical, literal (added in P5.1) | 3132.3 | 87.3 | 6361.2 | 193.3 | 3012.7 | 62.5 |

#### 4a, Python 3.10.20: the cache-key normalisation pass alone, after (µs)

| Tier | p50 | p99 |
|---|---|---|
| T1 point read | 2.5 | 4.5 |
| T2 join | 5.6 | 16.5 |
| T3 insert values | 2.2 | 3.4 |
| T4 insert-select | 3.0 | 5.6 |
| T5 analytical | 58.5 | 169.8 |
| L1 point read, literal (added in P5.1) | 3.2 | 7.3 |
| L3 insert values, literal (added in P5.1) | 4.2 | 8.1 |
| L5 analytical, literal (added in P5.1) | 59.1 | 113.6 |

### 4a, Python 3.11.15: `_capture` and `_classify` (µs)

| Tier | capture p50 before | after | capture p99 before | after | classify p50 before | after |
|---|---|---|---|---|---|---|
| T1 point read | 9.9 | 9.5 | 52.3 | 39.3 | 1.0 | 0.9 |
| T2 join | 16.7 | 16.3 | 50.7 | 50.2 | 1.3 | 1.2 |
| T3 insert values | 9.2 | 9.0 | 32.5 | 32.6 | 0.8 | 0.9 |
| T4 insert-select | 16.4 | 15.7 | 66.7 | 46.3 | 1.2 | 1.2 |
| T5 analytical | 16.6 | 17.2 | 52.3 | 75.9 | 1.2 | 1.3 |
| L1 point read, literal (added in P5.1) | 214.1 | 14.2 | 485.5 | 47.4 | 196.5 | 4.9 |
| L3 insert values, literal (added in P5.1) | 165.9 | 14.9 | 296.9 | 48.4 | 150.1 | 5.9 |
| L5 analytical, literal (added in P5.1) | 2311.6 | 86.4 | 4681.6 | 178.4 | 2303.6 | 65.5 |

#### 4a, Python 3.11.15: the cache-key normalisation pass alone, after (µs)

| Tier | p50 | p99 |
|---|---|---|
| T1 point read | 2.7 | 5.0 |
| T2 join | 5.8 | 11.5 |
| T3 insert values | 2.4 | 4.7 |
| T4 insert-select | 3.2 | 6.5 |
| T5 analytical | 59.8 | 131.0 |
| L1 point read, literal (added in P5.1) | 3.1 | 5.5 |
| L3 insert values, literal (added in P5.1) | 4.2 | 8.7 |
| L5 analytical, literal (added in P5.1) | 62.4 | 104.3 |

### 4a, Python 3.12.3: `_capture` and `_classify` (µs)

| Tier | capture p50 before | after | capture p99 before | after | classify p50 before | after |
|---|---|---|---|---|---|---|
| T1 point read | 9.7 | 9.7 | 34.2 | 33.2 | 0.9 | 0.9 |
| T2 join | 17.7 | 17.5 | 56.3 | 49.0 | 1.2 | 1.3 |
| T3 insert values | 9.2 | 9.2 | 34.6 | 31.0 | 0.8 | 0.9 |
| T4 insert-select | 17.0 | 16.8 | 50.0 | 47.1 | 1.3 | 1.3 |
| T5 analytical | 17.6 | 17.4 | 53.1 | 46.6 | 1.3 | 1.3 |
| L1 point read, literal (added in P5.1) | 212.5 | 14.7 | 504.6 | 52.5 | 186.5 | 4.9 |
| L3 insert values, literal (added in P5.1) | 162.1 | 15.4 | 418.9 | 55.7 | 145.1 | 5.9 |
| L5 analytical, literal (added in P5.1) | 2367.9 | 80.8 | 5366.3 | 133.3 | 2294.0 | 58.3 |

#### 4a, Python 3.12.3: the cache-key normalisation pass alone, after (µs)

| Tier | p50 | p99 |
|---|---|---|
| T1 point read | 2.5 | 4.2 |
| T2 join | 5.3 | 9.7 |
| T3 insert values | 2.2 | 3.9 |
| T4 insert-select | 2.9 | 5.3 |
| T5 analytical | 54.1 | 105.5 |
| L1 point read, literal (added in P5.1) | 3.1 | 7.4 |
| L3 insert values, literal (added in P5.1) | 4.3 | 14.4 |
| L5 analytical, literal (added in P5.1) | 57.7 | 95.3 |

### 4a, Python 3.13.14: `_capture` and `_classify` (µs)

| Tier | capture p50 before | after | capture p99 before | after | classify p50 before | after |
|---|---|---|---|---|---|---|
| T1 point read | 9.3 | 9.4 | 39.1 | 33.9 | 0.8 | 0.8 |
| T2 join | 16.5 | 16.7 | 60.1 | 49.8 | 1.2 | 1.1 |
| T3 insert values | 8.8 | 8.8 | 44.6 | 31.3 | 0.7 | 0.7 |
| T4 insert-select | 16.0 | 16.1 | 46.6 | 46.3 | 1.1 | 1.1 |
| T5 analytical | 16.7 | 16.8 | 51.1 | 46.5 | 1.2 | 1.2 |
| L1 point read, literal (added in P5.1) | 217.9 | 14.6 | 580.5 | 54.0 | 215.6 | 4.8 |
| L3 insert values, literal (added in P5.1) | 172.1 | 15.0 | 542.9 | 51.4 | 152.4 | 5.9 |
| L5 analytical, literal (added in P5.1) | 2497.9 | 90.9 | 4805.0 | 238.9 | 2396.0 | 66.9 |

#### 4a, Python 3.13.14: the cache-key normalisation pass alone, after (µs)

| Tier | p50 | p99 |
|---|---|---|
| T1 point read | 2.9 | 7.8 |
| T2 join | 6.2 | 10.6 |
| T3 insert values | 2.5 | 4.3 |
| T4 insert-select | 3.4 | 6.6 |
| T5 analytical | 62.8 | 137.1 |
| L1 point read, literal (added in P5.1) | 3.4 | 6.9 |
| L3 insert values, literal (added in P5.1) | 4.4 | 25.5 |
| L5 analytical, literal (added in P5.1) | 65.1 | 145.9 |

### 4a, Python 3.14.8: `_capture` and `_classify` (µs)

| Tier | capture p50 before | after | capture p99 before | after | classify p50 before | after |
|---|---|---|---|---|---|---|
| T1 point read | 7.4 | 7.4 | 27.6 | 37.8 | 0.7 | 0.7 |
| T2 join | 13.0 | 13.8 | 45.4 | 67.2 | 1.0 | 1.1 |
| T3 insert values | 7.0 | 7.0 | 20.9 | 34.0 | 0.7 | 0.7 |
| T4 insert-select | 12.5 | 12.7 | 42.4 | 52.5 | 1.1 | 1.1 |
| T5 analytical | 13.0 | 13.0 | 41.9 | 52.9 | 1.0 | 1.1 |
| L1 point read, literal (added in P5.1) | 189.9 | 11.2 | 608.2 | 41.5 | 169.4 | 4.2 |
| L3 insert values, literal (added in P5.1) | 146.0 | 12.0 | 520.4 | 57.8 | 131.1 | 5.4 |
| L5 analytical, literal (added in P5.1) | 2171.9 | 69.8 | 4283.5 | 142.2 | 2082.8 | 54.5 |

#### 4a, Python 3.14.8: the cache-key normalisation pass alone, after (µs)

| Tier | p50 | p99 |
|---|---|---|
| T1 point read | 2.3 | 5.0 |
| T2 join | 5.0 | 13.8 |
| T3 insert values | 2.2 | 3.9 |
| T4 insert-select | 2.8 | 6.2 |
| T5 analytical | 49.6 | 116.0 |
| L1 point read, literal (added in P5.1) | 2.9 | 6.1 |
| L3 insert values, literal (added in P5.1) | 4.1 | 8.4 |
| L5 analytical, literal (added in P5.1) | 52.6 | 101.7 |

### 4b, T1 point read

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +59.0 [+52.2, +67.0] | +63.9 [+54.2, +73.3] | +114.1 [+73.2, +154.3] | +187.1 [+142.6, +226.5] | met → met | -34.24% [-37.62, -31.20] | -36.65% [-40.00, -33.21] | not met → not met | +65.1 [+57.2, +74.2] | +72.4 [+63.8, +81.0] |
| http | +52.0 [+44.5, +59.7] | +53.9 [+42.3, +65.8] | +453.2 [+367.7, +542.5] | +546.0 [+491.1, +599.6] | met → met | -36.25% [-40.31, -32.17] | -36.60% [-41.26, -31.64] | not met → not met | +71.1 [+61.5, +81.1] | +73.2 [+60.7, +86.0] |
| http-down | +51.1 [+40.2, +61.1] | +44.2 [+35.6, +52.6] | +92.2 [+38.1, +140.9] | +86.9 [+51.5, +124.7] | met → met | -29.96% [-35.19, -24.12] | -27.08% [-30.30, -23.42] | not met → not met | +54.1 [+42.3, +64.9] | +46.6 [+39.2, +53.9] |
| file+sqlcomment | +74.0 [+63.5, +84.6] | +80.5 [+71.8, +89.3] | +143.2 [+81.2, +204.9] | +164.6 [+115.4, +224.7] | met → met | -39.75% [-45.00, -34.28] | -41.47% [-44.94, -37.77] | not met → not met | +83.6 [+69.2, +97.9] | +88.9 [+78.2, +99.7] |
| wrap-only | +2.7 [-5.3, +9.9] | +1.0 [-4.1, +6.5] | +26.5 [-29.8, +81.2] | +79.9 [+26.0, +139.0] | met → met | -2.47% [-9.87, +5.61] | -3.79% [-8.18, +0.77] | inconclusive → inconclusive | +3.9 [-6.2, +13.5] | +5.3 [-0.4, +10.9] |
| capture-null | +48.7 [+39.5, +59.2] | +42.0 [+31.3, +54.0] | +102.0 [+61.7, +141.5] | +100.0 [+69.0, +132.9] | met → met | -29.46% [-33.32, -25.45] | -26.03% [-30.23, -21.38] | not met → not met | +52.1 [+44.2, +60.2] | +44.6 [+35.5, +53.5] |

#### Attribution, T1 point read

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | +2.7 [-5.3, +9.9] | +1.0 [-4.1, +6.5] | +3.9 [-6.2, +13.5] | +5.3 [-0.4, +10.9] |
| capture + construction | `capture-null − wrap-only` | +46.0 [+35.9, +56.6] | +41.0 [+30.0, +53.4] | +48.2 [+40.8, +55.3] | +39.2 [+30.3, +49.1] |
| async enqueue | `http-down − capture-null` | +2.4 [-5.7, +11.3] | +2.2 [-7.9, +12.7] | +2.0 [-4.0, +9.1] | +2.0 [-6.3, +10.9] |
| synchronous file write | `file − http-down` | +7.9 [-5.0, +20.8] | +19.6 [+5.5, +33.2] | +11.1 [-3.7, +25.4] | +25.8 [+13.3, +37.1] |
| SQL comment | `file+sqlcomment − file` | +15.0 [+3.1, +26.3] | +16.6 [+10.5, +22.6] | +18.5 [+2.6, +33.9] | +16.5 [+10.0, +23.9] |

### 4b, T2 join

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +73.5 [+65.6, +81.6] | +91.1 [+80.2, +105.8] | +167.2 [+107.4, +231.0] | +168.6 [+115.9, +213.7] | met → met | -39.19% [-43.21, -35.29] | -42.94% [-45.67, -40.22] | not met → not met | +85.7 [+74.1, +99.0] | +100.0 [+90.9, +110.4] |
| http | +63.9 [+52.9, +77.2] | +58.4 [+53.5, +64.0] | +238.8 [+181.7, +295.2] | +270.4 [+177.7, +381.5] | met → met | -38.64% [-43.70, -34.13] | -36.68% [-39.31, -34.21] | not met → not met | +84.4 [+70.7, +100.5] | +77.0 [+69.5, +85.3] |
| http-down | +60.1 [+53.9, +66.2] | +58.9 [+53.0, +64.6] | +181.8 [+147.5, +218.8] | +116.7 [+76.1, +160.7] | met → met | -37.45% [-39.62, -35.33] | -35.89% [-38.28, -33.45] | not met → not met | +78.4 [+73.0, +84.2] | +74.0 [+68.1, +80.0] |
| file+sqlcomment | +102.2 [+94.1, +109.7] | +107.4 [+98.2, +117.7] | +230.0 [+186.5, +287.7] | +169.8 [+121.0, +223.4] | met → met | -46.57% [-49.08, -43.94] | -46.66% [-49.37, -44.17] | not met → not met | +114.5 [+105.3, +123.4] | +116.8 [+105.0, +130.2] |
| wrap-only | -2.4 [-8.6, +3.5] | +1.5 [-5.1, +8.9] | +31.0 [+0.1, +66.7] | -25.3 [-72.4, +13.0] | met → met | +0.11% [-4.51, +4.80] | +0.39% [-5.07, +5.49] | inconclusive → inconclusive | +0.2 [-6.0, +6.6] | +0.2 [-6.6, +7.5] |
| capture-null | +56.3 [+46.5, +66.0] | +40.1 [+34.4, +45.8] | +142.9 [+105.9, +183.2] | +88.3 [+48.9, +118.9] | met → met | -32.78% [-36.18, -29.61] | -25.75% [-28.89, -22.27] | not met → not met | +64.5 [+56.2, +73.6] | +46.3 [+38.9, +53.3] |

#### Attribution, T2 join

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | -2.4 [-8.6, +3.5] | +1.5 [-5.1, +8.9] | +0.2 [-6.0, +6.6] | +0.2 [-6.6, +7.5] |
| capture + construction | `capture-null − wrap-only` | +58.7 [+46.5, +71.1] | +38.6 [+29.5, +47.6] | +64.2 [+52.1, +75.8] | +46.1 [+37.1, +56.1] |
| async enqueue | `http-down − capture-null` | +3.8 [-7.4, +15.1] | +18.9 [+11.1, +28.1] | +13.9 [+2.7, +25.2] | +27.7 [+17.9, +37.9] |
| synchronous file write | `file − http-down` | +13.4 [+5.8, +22.1] | +32.2 [+20.0, +48.7] | +7.3 [-4.8, +21.5] | +26.0 [+16.0, +38.8] |
| SQL comment | `file+sqlcomment − file` | +28.6 [+18.7, +37.6] | +16.3 [-3.5, +32.8] | +28.8 [+12.6, +42.7] | +16.8 [-1.5, +35.2] |

### 4b, T3 insert values

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +103.7 [+75.5, +137.6] | +98.0 [+49.7, +145.5] | +274.0 [+113.5, +454.2] | +94.8 [-178.3, +332.9] | met → met | -20.64% [-27.20, -14.86] | -19.29% [-26.87, -10.30] | not met → not met | +112.9 [+76.4, +157.1] | +108.3 [+54.4, +158.3] |
| http | +118.5 [+85.2, +156.1] | +128.0 [+77.9, +184.5] | +375.8 [+280.8, +479.6] | +188.0 [-69.7, +435.2] | met → met | -23.69% [-28.70, -18.44] | -22.85% [-29.51, -15.76] | not met → not met | +133.1 [+98.2, +171.3] | +136.7 [+86.9, +191.3] |
| http-down | +87.8 [+48.2, +139.2] | +60.3 [+34.2, +87.8] | +170.3 [+68.3, +282.1] | -37.7 [-191.1, +108.6] | met → met | -16.55% [-23.24, -9.80] | -11.83% [-18.06, -5.76] | not met → not met | +91.1 [+50.2, +141.3] | +62.5 [+29.8, +96.4] |
| file+sqlcomment | +124.0 [+86.8, +169.0] | +116.0 [+57.3, +178.5] | +279.3 [+152.4, +397.4] | +23.7 [-196.1, +203.5] | met → met | -24.32% [-29.85, -18.82] | -19.95% [-28.84, -10.25] | not met → not met | +140.1 [+99.9, +184.9] | +116.9 [+55.5, +183.3] |
| wrap-only | -7.4 [-48.3, +33.7] | +7.2 [-28.5, +40.9] | +15.6 [-113.3, +159.2] | -133.3 [-332.3, +56.5] | met → met | +4.43% [-6.59, +15.93] | +0.18% [-8.14, +9.36] | inconclusive → inconclusive | -9.5 [-53.5, +35.0] | +6.7 [-30.2, +43.4] |
| capture-null | +66.5 [+35.9, +94.8] | +47.5 [+12.8, +81.6] | +142.9 [+74.5, +210.8] | -35.7 [-242.1, +136.1] | met → met | -13.74% [-18.62, -7.66] | -8.86% [-15.73, -0.41] | not met → inconclusive | +68.2 [+37.8, +95.9] | +44.7 [+5.6, +81.1] |

#### Attribution, T3 insert values

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | -7.4 [-48.3, +33.7] | +7.2 [-28.5, +40.9] | -9.5 [-53.5, +35.0] | +6.7 [-30.2, +43.4] |
| capture + construction | `capture-null − wrap-only` | +73.8 [+40.6, +99.7] | +40.4 [+2.5, +74.1] | +77.8 [+43.1, +105.7] | +38.0 [-1.3, +72.8] |
| async enqueue | `http-down − capture-null` | +21.4 [-16.2, +65.0] | +12.8 [-15.7, +43.4] | +22.9 [-15.0, +66.2] | +17.8 [-12.3, +49.0] |
| synchronous file write | `file − http-down` | +15.9 [-40.5, +66.2] | +37.7 [-13.0, +83.0] | +21.8 [-38.4, +80.5] | +45.9 [-13.8, +102.4] |
| SQL comment | `file+sqlcomment − file` | +20.3 [-31.9, +72.2] | +18.0 [-22.0, +57.8] | +27.2 [-35.6, +84.2] | +8.5 [-48.7, +64.7] |

### 4b, T4 insert-select

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +199.7 [+155.5, +249.9] | +151.3 [+105.7, +197.2] | +510.9 [+313.9, +695.8] | +259.0 [+127.7, +385.6] | met → met | -32.84% [-36.85, -28.48] | -28.22% [-35.13, -21.22] | not met → not met | +209.8 [+164.0, +260.6] | +162.0 [+117.5, +207.6] |
| http | +145.1 [+110.2, +181.9] | +152.1 [+103.9, +203.7] | +478.8 [+350.7, +610.3] | +631.0 [+366.5, +936.2] | met → met | -28.53% [-34.33, -22.98] | -30.15% [-38.12, -22.59] | not met → not met | +168.2 [+129.9, +210.9] | +182.2 [+128.1, +238.3] |
| http-down | +92.2 [+57.4, +129.5] | +128.6 [+85.9, +171.9] | +131.1 [+13.4, +246.4] | +327.9 [+95.3, +581.6] | met → met | -18.46% [-25.41, -11.80] | -24.76% [-32.22, -17.28] | not met → not met | +95.3 [+60.3, +131.4] | +137.2 [+93.9, +179.6] |
| file+sqlcomment | +147.9 [+108.6, +183.8] | +187.5 [+150.1, +229.3] | +356.0 [+250.2, +477.5] | +399.2 [+238.8, +542.6] | met → met | -27.50% [-33.16, -21.21] | -33.09% [-39.21, -27.74] | not met → not met | +159.1 [+119.7, +195.5] | +202.5 [+162.3, +246.3] |
| wrap-only | +15.7 [-28.4, +59.3] | +13.0 [-30.3, +64.9] | -7.8 [-157.4, +137.1] | +6.4 [-121.2, +163.1] | met → met | -1.20% [-12.33, +10.72] | -2.66% [-13.93, +6.89] | inconclusive → inconclusive | +11.4 [-36.6, +58.2] | +19.1 [-25.6, +73.2] |
| capture-null | +75.4 [+39.2, +114.5] | +88.0 [+50.2, +128.5] | +135.3 [+51.6, +209.9] | +201.1 [+55.9, +370.2] | met → met | -16.19% [-23.25, -9.10] | -19.11% [-26.51, -12.04] | not met → not met | +81.3 [+44.9, +119.9] | +95.6 [+60.4, +132.7] |

#### Attribution, T4 insert-select

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | +15.7 [-28.4, +59.3] | +13.0 [-30.3, +64.9] | +11.4 [-36.6, +58.2] | +19.1 [-25.6, +73.2] |
| capture + construction | `capture-null − wrap-only` | +59.7 [+26.7, +88.1] | +75.0 [+43.5, +106.3] | +69.9 [+31.1, +104.7] | +76.5 [+39.6, +111.1] |
| async enqueue | `http-down − capture-null` | +16.8 [-0.8, +35.4] | +40.6 [+9.9, +72.8] | +13.9 [-11.9, +39.7] | +41.7 [+10.5, +71.6] |
| synchronous file write | `file − http-down` | +107.5 [+46.8, +168.5] | +22.7 [-10.6, +57.9] | +114.6 [+53.3, +175.3] | +24.7 [-14.8, +67.6] |
| SQL comment | `file+sqlcomment − file` | -51.8 [-114.4, +4.9] | +36.2 [-0.2, +72.7] | -50.7 [-116.7, +11.6] | +40.5 [+1.2, +79.7] |

### 4b, T5 analytical

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +104.1 [+83.6, +126.8] | +93.1 [+86.2, +100.9] | +184.3 [+95.4, +252.1] | +237.7 [+185.6, +289.8] | met → met | -34.33% [-38.90, -29.72] | -35.03% [-37.49, -32.56] | not met → not met | +109.8 [+88.3, +132.7] | +104.6 [+95.8, +113.3] |
| http | +74.9 [+60.6, +92.8] | +67.0 [+57.4, +76.7] | +696.5 [+628.5, +767.0] | +692.0 [+568.8, +812.9] | met → met | -31.56% [-35.88, -27.95] | -32.54% [-35.03, -29.71] | not met → not met | +95.8 [+79.6, +116.8] | +94.3 [+82.8, +105.0] |
| http-down | +66.2 [+57.7, +76.3] | +72.5 [+49.4, +94.4] | +108.6 [+35.6, +177.0] | +177.6 [+122.1, +235.4] | met → met | -25.08% [-28.52, -21.28] | -28.02% [-34.09, -21.09] | not met → not met | +68.6 [+56.9, +79.6] | +78.1 [+57.1, +97.5] |
| file+sqlcomment | +110.9 [+97.7, +123.5] | +113.4 [+98.8, +127.3] | +244.2 [+152.6, +329.2] | +262.0 [+201.0, +325.5] | met → met | -36.89% [-41.05, -32.65] | -40.09% [-43.45, -36.64] | not met → not met | +120.7 [+102.1, +139.9] | +130.6 [+116.5, +145.3] |
| wrap-only | -4.4 [-11.4, +3.0] | +2.3 [-11.6, +14.6] | -52.3 [-114.2, -1.1] | +11.1 [-32.5, +52.8] | met → met | +4.23% [-0.05, +9.00] | -1.16% [-6.72, +5.99] | met → inconclusive | -7.5 [-16.4, +0.6] | +2.9 [-10.5, +13.7] |
| capture-null | +55.6 [+47.2, +65.2] | +54.5 [+37.8, +70.7] | +124.6 [+44.7, +200.3] | +146.7 [+96.5, +193.7] | met → met | -23.60% [-27.35, -19.86] | -22.67% [-27.66, -16.97] | not met → not met | +63.5 [+51.8, +75.5] | +58.2 [+42.3, +72.8] |

#### Attribution, T5 analytical

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | -4.4 [-11.4, +3.0] | +2.3 [-11.6, +14.6] | -7.5 [-16.4, +0.6] | +2.9 [-10.5, +13.7] |
| capture + construction | `capture-null − wrap-only` | +60.0 [+48.9, +72.2] | +52.2 [+41.4, +63.0] | +71.0 [+60.4, +81.8] | +55.3 [+45.6, +64.8] |
| async enqueue | `http-down − capture-null` | +10.5 [-1.0, +24.2] | +18.0 [+0.9, +35.3] | +5.1 [-4.4, +17.5] | +19.9 [+5.7, +34.9] |
| synchronous file write | `file − http-down` | +38.0 [+15.1, +62.8] | +20.5 [+1.3, +41.0] | +41.2 [+16.7, +67.7] | +26.5 [+8.1, +47.2] |
| SQL comment | `file+sqlcomment − file` | +6.7 [-24.8, +36.2] | +20.3 [+7.6, +31.8] | +10.9 [-23.3, +42.9] | +26.0 [+13.8, +38.6] |

### 4b, L1 point read, literal (added in P5.1)

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +404.7 [+386.8, +426.5] | +74.7 [+65.9, +83.7] | +769.1 [+702.4, +849.2] | +191.9 [+147.3, +241.5] | met → met | -74.88% [-76.40, -73.31] | -36.03% [-39.21, -32.96] | not met → not met | +444.8 [+424.1, +471.0] | +83.3 [+73.8, +92.6] |
| http | +457.5 [+427.0, +494.6] | +79.0 [+68.9, +89.0] | +1036.1 [+973.6, +1099.2] | +528.6 [+474.0, +584.7] | inconclusive → met | -76.99% [-78.34, -75.44] | -41.03% [-43.84, -38.26] | not met → not met | +499.5 [+476.0, +527.1] | +102.6 [+93.2, +111.9] |
| http-down | +370.2 [+358.9, +381.3] | +60.7 [+49.3, +72.3] | +755.1 [+706.3, +798.5] | +129.8 [+71.5, +183.6] | met → met | -73.32% [-74.54, -71.96] | -31.04% [-35.44, -26.54] | not met → not met | +408.6 [+397.3, +419.6] | +67.1 [+55.4, +79.2] |
| file+sqlcomment | +414.7 [+393.5, +434.9] | +85.8 [+79.3, +91.8] | +827.1 [+740.9, +915.6] | +198.2 [+157.2, +242.8] | met → met | -75.60% [-77.30, -73.51] | -39.85% [-41.69, -38.15] | not met → not met | +464.0 [+437.1, +490.3] | +97.2 [+91.8, +102.7] |
| wrap-only | -4.0 [-15.8, +4.0] | +4.8 [-5.2, +16.2] | +8.8 [-24.3, +41.4] | +62.7 [+11.6, +120.6] | met → met | +1.60% [-4.99, +9.80] | -4.65% [-11.48, +1.43] | inconclusive → inconclusive | -1.7 [-13.4, +8.2] | +8.4 [-1.5, +20.1] |
| capture-null | +367.5 [+349.6, +388.5] | +57.2 [+48.9, +65.5] | +703.3 [+632.5, +784.2] | +183.5 [+140.6, +232.3] | met → met | -72.94% [-74.08, -71.22] | -30.28% [-33.33, -27.23] | not met → not met | +401.6 [+384.1, +420.7] | +64.2 [+56.1, +72.8] |

#### Attribution, L1 point read, literal (added in P5.1)

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | -4.0 [-15.8, +4.0] | +4.8 [-5.2, +16.2] | -1.7 [-13.4, +8.2] | +8.4 [-1.5, +20.1] |
| capture + construction | `capture-null − wrap-only` | +371.5 [+354.4, +390.6] | +52.4 [+39.6, +64.8] | +403.3 [+383.9, +423.9] | +55.8 [+41.0, +69.3] |
| async enqueue | `http-down − capture-null` | +2.7 [-22.4, +24.0] | +3.5 [-6.3, +14.0] | +7.0 [-16.5, +28.4] | +2.9 [-7.3, +13.8] |
| synchronous file write | `file − http-down` | +34.6 [+14.8, +56.5] | +14.0 [+5.0, +23.1] | +36.2 [+13.1, +62.0] | +16.1 [+5.1, +27.9] |
| SQL comment | `file+sqlcomment − file` | +10.0 [-18.1, +34.8] | +11.1 [+2.8, +19.5] | +19.2 [-13.4, +50.4] | +13.9 [+4.9, +23.5] |

### 4b, L3 insert values, literal (added in P5.1)

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +450.6 [+424.1, +481.5] | +86.7 [+53.2, +129.1] | +925.2 [+810.7, +1042.2] | +153.2 [+52.4, +271.1] | inconclusive → met | -52.91% [-55.78, -49.97] | -17.30% [-24.21, -11.35] | not met → not met | +477.4 [+450.9, +506.6] | +98.0 [+65.2, +137.1] |
| http | +527.8 [+478.9, +579.2] | +107.0 [+66.9, +149.1] | +1307.5 [+998.2, +1647.7] | +331.2 [+218.1, +449.8] | inconclusive → met | -56.45% [-60.47, -52.07] | -21.08% [-27.99, -14.61] | not met → not met | +557.4 [+501.6, +612.2] | +124.2 [+87.0, +166.3] |
| http-down | +409.1 [+353.2, +464.0] | +79.1 [-2.4, +143.6] | +816.8 [+620.0, +1047.2] | +103.5 [-73.9, +307.8] | inconclusive → met | -50.07% [-54.54, -45.27] | -13.41% [-24.22, +0.80] | not met → inconclusive | +434.8 [+375.0, +497.3] | +84.5 [+8.2, +147.5] |
| file+sqlcomment | +445.0 [+395.4, +484.7] | +98.7 [+63.0, +134.4] | +939.4 [+820.4, +1088.4] | +296.3 [+178.6, +396.9] | inconclusive → met | -52.44% [-56.23, -47.66] | -19.61% [-25.93, -13.04] | not met → not met | +473.3 [+419.9, +515.3] | +113.0 [+75.9, +149.7] |
| wrap-only | +10.7 [-30.8, +52.8] | -22.1 [-84.3, +29.3] | +108.4 [-38.6, +265.2] | -107.3 [-231.4, +12.1] | met → met | -1.70% [-11.29, +8.64] | +6.05% [-4.92, +20.12] | inconclusive → inconclusive | +12.3 [-31.8, +56.2] | -23.5 [-85.2, +26.0] |
| capture-null | +368.5 [+329.4, +405.7] | +48.6 [-26.0, +107.9] | +706.9 [+619.1, +812.6] | +108.7 [-84.5, +272.8] | met → met | -47.83% [-52.19, -42.90] | -9.21% [-20.77, +6.82] | not met → inconclusive | +391.2 [+350.8, +427.7] | +56.0 [-21.1, +115.4] |

#### Attribution, L3 insert values, literal (added in P5.1)

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | +10.7 [-30.8, +52.8] | -22.1 [-84.3, +29.3] | +12.3 [-31.8, +56.2] | -23.5 [-85.2, +26.0] |
| capture + construction | `capture-null − wrap-only` | +357.8 [+326.5, +387.3] | +70.7 [+39.3, +106.9] | +378.9 [+338.2, +414.9] | +79.5 [+45.3, +118.8] |
| async enqueue | `http-down − capture-null` | +40.6 [-16.8, +103.5] | +30.5 [-15.1, +76.4] | +43.5 [-19.9, +112.3] | +28.5 [-18.7, +74.7] |
| synchronous file write | `file − http-down` | +41.5 [-25.9, +116.2] | +7.6 [-44.2, +75.4] | +42.7 [-24.7, +115.1] | +13.5 [-38.2, +79.0] |
| SQL comment | `file+sqlcomment − file` | -5.6 [-68.1, +50.3] | +12.0 [-17.1, +41.5] | -4.1 [-63.8, +51.1] | +15.0 [-16.2, +46.1] |

### 4b, L5 analytical, literal (added in P5.1)

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +2914.7 [+2829.2, +3010.5] | +257.8 [+230.8, +286.3] | +6294.0 [+5989.2, +6602.1] | +444.3 [+365.0, +558.5] | not met → met | -86.03% [-86.52, -85.55] | -32.51% [-34.75, -30.40] | not met → not met | +3304.3 [+3195.4, +3424.5] | +257.8 [+235.3, +281.7] |
| http | +3205.1 [+3173.8, +3240.0] | +286.1 [+264.0, +310.0] | +6635.0 [+6424.3, +6887.9] | +618.8 [+493.6, +760.7] | not met → met | -86.90% [-87.19, -86.58] | -35.41% [-37.57, -33.38] | not met → not met | +3551.7 [+3517.7, +3588.1] | +293.4 [+269.4, +319.1] |
| http-down | +2773.1 [+2726.2, +2828.6] | +211.7 [+186.2, +237.1] | +5943.9 [+5671.7, +6245.0] | +289.8 [+193.6, +392.0] | not met → met | -85.42% [-85.93, -84.90] | -28.23% [-31.11, -25.00] | not met → not met | +3141.8 [+3075.7, +3216.7] | +211.4 [+182.8, +238.0] |
| file+sqlcomment | +2875.6 [+2802.8, +2954.6] | +288.9 [+262.4, +311.8] | +6353.1 [+6146.3, +6553.7] | +565.2 [+462.9, +681.3] | not met → met | -85.84% [-86.40, -85.21] | -35.58% [-37.30, -33.57] | not met → not met | +3253.7 [+3151.8, +3346.4] | +295.1 [+273.0, +314.8] |
| wrap-only | -1.8 [-19.9, +19.0] | +11.4 [-1.8, +24.4] | -3.3 [-91.3, +90.8] | +28.1 [-50.3, +120.8] | met → met | +0.09% [-4.39, +4.43] | -1.57% [-4.05, +1.22] | inconclusive → inconclusive | +0.9 [-22.7, +25.8] | +9.0 [-5.8, +22.2] |
| capture-null | +2822.0 [+2744.7, +2909.0] | +211.6 [+182.2, +242.8] | +6132.0 [+5756.5, +6461.5] | +454.5 [+312.5, +620.7] | not met → met | -85.58% [-86.17, -85.00] | -28.61% [-32.08, -25.19] | not met → not met | +3187.0 [+3065.6, +3318.9] | +216.4 [+183.9, +249.9] |

#### Attribution, L5 analytical, literal (added in P5.1)

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | -1.8 [-19.9, +19.0] | +11.4 [-1.8, +24.4] | +0.9 [-22.7, +25.8] | +9.0 [-5.8, +22.2] |
| capture + construction | `capture-null − wrap-only` | +2823.8 [+2747.8, +2913.1] | +200.2 [+176.9, +226.1] | +3186.1 [+3066.3, +3320.4] | +207.3 [+181.0, +234.9] |
| async enqueue | `http-down − capture-null` | -49.0 [-141.0, +23.6] | +0.2 [-30.5, +32.3] | -45.2 [-186.0, +71.1] | -5.0 [-32.7, +27.2] |
| synchronous file write | `file − http-down` | +141.7 [+48.6, +246.9] | +46.0 [+21.7, +72.4] | +162.5 [+28.6, +308.5] | +46.4 [+25.6, +66.9] |
| SQL comment | `file+sqlcomment − file` | -39.1 [-173.0, +79.5] | +31.1 [+0.5, +62.3] | -50.6 [-217.6, +90.2] | +37.3 [+12.7, +62.2] |

### 4b, Kafka `produce()`

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +24.8 [+23.4, +26.8] | +25.9 [+24.9, +27.5] | +80.1 [+67.8, +92.5] | +84.2 [+78.9, +89.5] | met → met | -81.72% [-86.36, -76.87] | -84.24% [-89.57, -78.34] | not met → not met | +26.0 [+22.8, +29.7] | +27.5 [+24.7, +30.4] |
| http | +49.1 [+46.5, +52.2] | +47.6 [+46.1, +49.1] | +122.1 [+106.9, +138.8] | +114.1 [+102.4, +127.6] | met → met | -89.25% [-92.26, -86.06] | -90.29% [-93.20, -87.26] | not met → not met | +49.2 [+43.1, +55.4] | +46.3 [+41.9, +51.1] |
| wrap-only | +0.4 [+0.2, +0.6] | +0.5 [+0.3, +0.7] | -1.1 [-6.6, +2.2] | +1.5 [+0.6, +2.2] | met → met | +37.94% [+2.64, +76.52] | +63.28% [+5.92, +127.44] | met → met | -1.2 [-2.5, +0.1] | -1.7 [-3.5, +0.1] |
| capture-null | +15.6 [+14.7, +16.9] | +15.1 [+14.8, +15.3] | +62.8 [+53.5, +72.6] | +55.4 [+50.8, +60.6] | met → met | -72.26% [-79.31, -65.06] | -73.60% [-82.70, -63.46] | not met → not met | +15.0 [+13.1, +17.0] | +14.5 [+12.1, +16.7] |

#### Attribution, Kafka `produce()`

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | +0.4 [+0.2, +0.6] | +0.5 [+0.3, +0.7] | -1.2 [-2.5, +0.1] | -1.7 [-3.5, +0.1] |
| capture + construction | `capture-null − wrap-only` | +15.1 [+14.3, +16.5] | +14.6 [+14.3, +14.9] | +16.2 [+14.3, +18.0] | +16.1 [+14.9, +17.4] |
| enqueue (http, live backend) | `http − capture-null` | +33.5 [+30.4, +37.0] | +32.5 [+31.0, +34.1] | +34.2 [+28.1, +40.4] | +31.8 [+27.2, +36.9] |
| synchronous file write | `file − capture-null` | +9.3 [+6.9, +11.7] | +10.9 [+10.0, +12.3] | +11.0 [+7.4, +15.0] | +13.0 [+12.0, +14.0] |

### The fixed cost per call and the < 2% throughput target (after)

From the after run's implied added µs per call (point estimate). A fixed cost c per call takes c / (q + c) of the throughput of a query whose own latency is q, so the loss is under 2% once q > 49 × c. The last columns apply each cost to representative query latencies.

| Tier | Config | Implied µs/call [95% CI] | Loss < 2% for queries slower than (µs) | Loss at a 1 ms query | Loss at a 10 ms query | Loss at a 100 ms query |
|---|---|---|---|---|---|---|
| T1 point read | file | +72.4 [+63.8, +81.0] | 3546.1 | 6.75% | 0.72% | 0.07% |
| T1 point read | http | +73.2 [+60.7, +86.0] | 3588.9 | 6.82% | 0.73% | 0.07% |
| T1 point read | http-down | +46.6 [+39.2, +53.9] | 2283.6 | 4.45% | 0.46% | 0.05% |
| T1 point read | file+sqlcomment | +88.9 [+78.2, +99.7] | 4354.9 | 8.16% | 0.88% | 0.09% |
| T2 join | file | +100.0 [+90.9, +110.4] | 4901.4 | 9.09% | 0.99% | 0.10% |
| T2 join | http | +77.0 [+69.5, +85.3] | 3770.6 | 7.15% | 0.76% | 0.08% |
| T2 join | http-down | +74.0 [+68.1, +80.0] | 3628.1 | 6.89% | 0.73% | 0.07% |
| T2 join | file+sqlcomment | +116.8 [+105.0, +130.2] | 5723.2 | 10.46% | 1.15% | 0.12% |
| T3 insert values | file | +108.3 [+54.4, +158.3] | 5308.8 | 9.78% | 1.07% | 0.11% |
| T3 insert values | http | +136.7 [+86.9, +191.3] | 6697.1 | 12.02% | 1.35% | 0.14% |
| T3 insert values | http-down | +62.5 [+29.8, +96.4] | 3062.1 | 5.88% | 0.62% | 0.06% |
| T3 insert values | file+sqlcomment | +116.9 [+55.5, +183.3] | 5727.1 | 10.46% | 1.16% | 0.12% |
| T4 insert-select | file | +162.0 [+117.5, +207.6] | 7936.7 | 13.94% | 1.59% | 0.16% |
| T4 insert-select | http | +182.2 [+128.1, +238.3] | 8928.1 | 15.41% | 1.79% | 0.18% |
| T4 insert-select | http-down | +137.2 [+93.9, +179.6] | 6724.6 | 12.07% | 1.35% | 0.14% |
| T4 insert-select | file+sqlcomment | +202.5 [+162.3, +246.3] | 9921.7 | 16.84% | 1.98% | 0.20% |
| T5 analytical | file | +104.6 [+95.8, +113.3] | 5125.4 | 9.47% | 1.04% | 0.10% |
| T5 analytical | http | +94.3 [+82.8, +105.0] | 4620.5 | 8.62% | 0.93% | 0.09% |
| T5 analytical | http-down | +78.1 [+57.1, +97.5] | 3827.7 | 7.25% | 0.78% | 0.08% |
| T5 analytical | file+sqlcomment | +130.6 [+116.5, +145.3] | 6401.8 | 11.56% | 1.29% | 0.13% |
| L1 point read, literal (added in P5.1) | file | +83.3 [+73.8, +92.6] | 4080.5 | 7.69% | 0.83% | 0.08% |
| L1 point read, literal (added in P5.1) | http | +102.6 [+93.2, +111.9] | 5028.5 | 9.31% | 1.02% | 0.10% |
| L1 point read, literal (added in P5.1) | http-down | +67.1 [+55.4, +79.2] | 3290.0 | 6.29% | 0.67% | 0.07% |
| L1 point read, literal (added in P5.1) | file+sqlcomment | +97.2 [+91.8, +102.7] | 4763.8 | 8.86% | 0.96% | 0.10% |
| L3 insert values, literal (added in P5.1) | file | +98.0 [+65.2, +137.1] | 4803.2 | 8.93% | 0.97% | 0.10% |
| L3 insert values, literal (added in P5.1) | http | +124.2 [+87.0, +166.3] | 6086.4 | 11.05% | 1.23% | 0.12% |
| L3 insert values, literal (added in P5.1) | http-down | +84.5 [+8.2, +147.5] | 4140.1 | 7.79% | 0.84% | 0.08% |
| L3 insert values, literal (added in P5.1) | file+sqlcomment | +113.0 [+75.9, +149.7] | 5537.5 | 10.15% | 1.12% | 0.11% |
| L5 analytical, literal (added in P5.1) | file | +257.8 [+235.3, +281.7] | 12631.1 | 20.49% | 2.51% | 0.26% |
| L5 analytical, literal (added in P5.1) | http | +293.4 [+269.4, +319.1] | 14377.8 | 22.69% | 2.85% | 0.29% |
| L5 analytical, literal (added in P5.1) | http-down | +211.4 [+182.8, +238.0] | 10358.8 | 17.45% | 2.07% | 0.21% |
| L5 analytical, literal (added in P5.1) | file+sqlcomment | +295.1 [+273.0, +314.8] | 14459.2 | 22.78% | 2.87% | 0.29% |
| Kafka `produce()` | file | +27.5 [+24.7, +30.4] | 1345.7 | 2.67% | 0.27% | 0.03% |
| Kafka `produce()` | http | +46.3 [+41.9, +51.1] | 2269.0 | 4.43% | 0.46% | 0.05% |

### Process start-up (ms)

| Command | p50 before | after | p95 before | after |
|---|---|---|---|---|
| python | 14.1 | 14.7 | 15.5 | 20.1 |
| dcp-instrument python | 432.2 | 101.2 | 453.9 | 124.2 |
| python with DCP's sitecustomize | 264.5 | 59.2 | 315.3 | 71.0 |
| python, importing psycopg and confluent_kafka (added in P5.1) | 183.9 | 200.6 | 201.1 | 243.6 |
| dcp-instrument python, importing psycopg and confluent_kafka (added in P5.1) | 421.7 | 250.7 | 482.5 | 293.0 |
