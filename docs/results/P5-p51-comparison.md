# P5.1: the optimisations (O1 to O3, A5), before (`p51-before`) and after (`p51-after`)

Rendered by `benchmarks/render.py --compare` from the two runs' results JSON. Do not edit by hand.

|  | Before | After |
|---|---|---|
| Git commit | `9cf6e7d700f9495a7f5a5e45de113bef1d691194` | `d4c3ba5da2926ccad92b7c3a639443c637afddf8` |
| Command | `python benchmarks/run.py --label p51-before --only cpu,overhead --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.10/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.12/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.14/bin/python` | `python benchmarks/run.py --label p51-after --only cpu,overhead --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.10/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.12/bin/python --cpu-python /tmp/claude-0/-home-user-Wiretap/828f9579-6ded-5d5d-8cf4-a74ce8cb398f/scratchpad/p51-3.14/bin/python` |
| Started (UTC) | 2026-10-03T19:45:24+00:00 | 2026-10-03T20:34:23+00:00 |

### 4a, Python 3.10.20: `_capture` and `_classify` (µs)

| Tier | capture p50 before | after | capture p99 before | after | classify p50 before | after |
|---|---|---|---|---|---|---|
| T1 point read | 10.4 | 10.5 | 34.2 | 48.8 | 0.9 | 0.9 |
| T2 join | 17.9 | 17.7 | 48.2 | 55.5 | 1.4 | 1.3 |
| T3 insert values | 9.9 | 9.8 | 34.8 | 34.5 | 0.9 | 0.9 |
| T4 insert-select | 17.2 | 17.1 | 46.2 | 63.6 | 1.4 | 1.4 |
| T5 analytical | 18.1 | 17.8 | 48.1 | 55.0 | 1.3 | 1.4 |
| L1 point read, literal (added in P5.1) | 271.8 | 16.7 | 539.0 | 53.4 | 251.9 | 5.0 |
| L3 insert values, literal (added in P5.1) | 214.4 | 17.4 | 494.6 | 52.6 | 191.0 | 6.1 |
| L5 analytical, literal (added in P5.1) | 3049.0 | 87.0 | 6037.6 | 199.7 | 2996.4 | 62.2 |

#### 4a, Python 3.10.20: the cache-key normalisation pass alone, after (µs)

| Tier | p50 | p99 |
|---|---|---|
| T1 point read | 2.5 | 6.3 |
| T2 join | 5.6 | 10.6 |
| T3 insert values | 2.2 | 3.4 |
| T4 insert-select | 3.1 | 7.1 |
| T5 analytical | 58.3 | 104.3 |
| L1 point read, literal (added in P5.1) | 3.2 | 7.4 |
| L3 insert values, literal (added in P5.1) | 4.2 | 9.4 |
| L5 analytical, literal (added in P5.1) | 58.9 | 93.0 |

### 4a, Python 3.12.3: `_capture` and `_classify` (µs)

| Tier | capture p50 before | after | capture p99 before | after | classify p50 before | after |
|---|---|---|---|---|---|---|
| T1 point read | 9.8 | 9.7 | 33.1 | 34.4 | 0.9 | 0.9 |
| T2 join | 17.7 | 17.3 | 51.1 | 48.5 | 1.3 | 1.3 |
| T3 insert values | 9.3 | 9.2 | 35.1 | 36.8 | 0.8 | 0.8 |
| T4 insert-select | 17.1 | 16.9 | 69.7 | 52.2 | 2.0 | 1.3 |
| T5 analytical | 17.7 | 17.5 | 46.7 | 56.3 | 1.3 | 1.3 |
| L1 point read, literal (added in P5.1) | 207.3 | 14.5 | 440.5 | 47.0 | 185.9 | 4.8 |
| L3 insert values, literal (added in P5.1) | 160.6 | 15.1 | 343.8 | 45.9 | 144.6 | 5.8 |
| L5 analytical, literal (added in P5.1) | 2361.1 | 81.8 | 5285.8 | 194.5 | 2299.3 | 58.4 |

#### 4a, Python 3.12.3: the cache-key normalisation pass alone, after (µs)

| Tier | p50 | p99 |
|---|---|---|
| T1 point read | 2.5 | 3.2 |
| T2 join | 5.3 | 9.8 |
| T3 insert values | 2.2 | 5.0 |
| T4 insert-select | 3.0 | 6.8 |
| T5 analytical | 54.1 | 96.0 |
| L1 point read, literal (added in P5.1) | 3.1 | 5.4 |
| L3 insert values, literal (added in P5.1) | 4.2 | 8.3 |
| L5 analytical, literal (added in P5.1) | 56.5 | 137.4 |

### 4a, Python 3.14.8: `_capture` and `_classify` (µs)

| Tier | capture p50 before | after | capture p99 before | after | classify p50 before | after |
|---|---|---|---|---|---|---|
| T1 point read | 7.5 | 8.2 | 30.5 | 43.0 | 0.7 | 0.7 |
| T2 join | 13.6 | 13.0 | 47.3 | 41.0 | 1.1 | 1.1 |
| T3 insert values | 7.3 | 7.0 | 28.2 | 35.3 | 0.7 | 1.1 |
| T4 insert-select | 13.0 | 12.4 | 41.6 | 39.1 | 1.1 | 1.1 |
| T5 analytical | 13.4 | 13.0 | 41.2 | 42.1 | 1.1 | 1.0 |
| L1 point read, literal (added in P5.1) | 191.7 | 11.2 | 637.2 | 39.9 | 174.9 | 4.3 |
| L3 insert values, literal (added in P5.1) | 146.8 | 11.9 | 608.3 | 40.1 | 130.6 | 5.3 |
| L5 analytical, literal (added in P5.1) | 2143.7 | 70.5 | 4269.0 | 180.1 | 2088.7 | 54.3 |

#### 4a, Python 3.14.8: the cache-key normalisation pass alone, after (µs)

| Tier | p50 | p99 |
|---|---|---|
| T1 point read | 2.3 | 4.8 |
| T2 join | 5.0 | 25.8 |
| T3 insert values | 2.1 | 3.8 |
| T4 insert-select | 2.8 | 4.9 |
| T5 analytical | 50.1 | 127.6 |
| L1 point read, literal (added in P5.1) | 3.0 | 4.7 |
| L3 insert values, literal (added in P5.1) | 4.1 | 7.7 |
| L5 analytical, literal (added in P5.1) | 53.9 | 144.2 |

### 4b, T1 point read

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +62.1 [+52.6, +71.7] | +77.0 [+62.4, +91.1] | +99.3 [+56.0, +145.9] | +143.9 [+100.0, +186.6] | met → met | -34.17% [-38.01, -30.31] | -38.00% [-43.24, -32.69] | not met → not met | +66.9 [+57.7, +76.3] | +81.8 [+67.9, +96.0] |
| http | +49.7 [+42.0, +58.5] | +46.9 [+34.4, +60.3] | +456.8 [+387.4, +517.1] | +449.4 [+387.2, +516.0] | met → met | -33.98% [-38.08, -30.29] | -32.46% [-37.87, -27.28] | not met → not met | +66.4 [+57.5, +76.9] | +64.7 [+51.7, +79.5] |
| http-down | +46.9 [+40.2, +57.0] | +48.0 [+35.5, +61.3] | +54.2 [+11.3, +98.7] | +112.2 [+63.9, +162.8] | met → met | -28.38% [-32.34, -25.17] | -28.97% [-33.18, -24.93] | not met → not met | +51.0 [+44.1, +60.2] | +54.2 [+44.9, +64.2] |
| file+sqlcomment | +74.8 [+65.8, +84.2] | +94.1 [+82.1, +106.1] | +127.0 [+87.9, +157.0] | +147.7 [+92.7, +204.9] | met → met | -39.02% [-42.63, -35.34] | -42.78% [-47.83, -37.86] | not met → not met | +82.4 [+72.4, +92.3] | +100.0 [+84.5, +115.6] |
| wrap-only | +1.1 [-7.4, +9.3] | +1.1 [-7.9, +10.1] | -38.5 [-85.9, +6.2] | -3.6 [-43.7, +35.1] | met → met | +0.23% [-6.14, +7.22] | -0.99% [-6.99, +4.94] | inconclusive → inconclusive | +0.5 [-8.2, +8.8] | +1.5 [-6.2, +9.4] |
| capture-null | +34.8 [+27.7, +41.4] | +36.7 [+22.1, +53.3] | +39.2 [-2.8, +75.8] | +69.2 [+7.9, +129.6] | met → met | -22.65% [-26.15, -18.91] | -22.35% [-30.07, -14.89] | not met → not met | +37.7 [+30.8, +44.3] | +40.0 [+25.3, +56.6] |

#### Attribution, T1 point read

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | +1.1 [-7.4, +9.3] | +1.1 [-7.9, +10.1] | +0.5 [-8.2, +8.8] | +1.5 [-6.2, +9.4] |
| capture + construction | `capture-null − wrap-only` | +33.7 [+24.3, +43.3] | +35.6 [+25.0, +48.7] | +37.2 [+27.6, +46.8] | +38.5 [+29.2, +49.7] |
| async enqueue | `http-down − capture-null` | +12.1 [+3.8, +20.8] | +11.4 [-8.0, +28.7] | +13.3 [+3.8, +23.1] | +14.2 [-5.1, +30.6] |
| synchronous file write | `file − http-down` | +15.2 [+7.7, +23.1] | +29.0 [+12.0, +45.6] | +15.9 [+9.6, +22.6] | +27.7 [+12.8, +43.9] |
| SQL comment | `file+sqlcomment − file` | +12.8 [+1.6, +22.6] | +17.0 [+5.8, +29.6] | +15.5 [+4.2, +26.4] | +18.1 [+5.4, +32.7] |

### 4b, T2 join

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +83.9 [+79.5, +88.8] | +131.8 [+120.2, +143.4] | +185.7 [+128.1, +253.8] | +255.2 [+170.6, +352.2] | met → met | -41.70% [-43.59, -39.77] | -49.95% [-53.16, -46.59] | not met → not met | +95.4 [+88.6, +102.1] | +143.1 [+129.3, +156.9] |
| http | +67.8 [+59.8, +76.6] | +49.2 [+34.8, +61.6] | +330.1 [+235.1, +447.5] | +219.7 [+139.3, +324.8] | met → met | -39.24% [-42.13, -36.30] | -31.10% [-35.91, -25.38] | not met → not met | +86.5 [+77.6, +96.1] | +65.4 [+51.9, +77.2] |
| http-down | +59.7 [+53.4, +65.4] | +52.8 [+38.2, +67.4] | +127.7 [+96.3, +158.8] | +173.1 [+105.1, +240.9] | met → met | -36.78% [-39.16, -34.40] | -33.18% [-39.03, -26.98] | not met → not met | +77.5 [+71.5, +83.9] | +72.8 [+56.6, +89.1] |
| file+sqlcomment | +104.4 [+98.1, +111.7] | +170.3 [+158.7, +181.9] | +221.3 [+169.8, +286.8] | +265.7 [+191.5, +352.6] | met → met | -46.91% [-48.85, -45.11] | -54.82% [-57.55, -51.97] | not met → not met | +117.8 [+110.2, +126.5] | +173.4 [+160.4, +186.9] |
| wrap-only | -1.2 [-11.1, +9.2] | -1.9 [-14.4, +7.1] | -3.0 [-41.5, +36.8] | -35.8 [-69.8, -5.9] | met → met | +1.45% [-5.90, +8.54] | +3.19% [-3.29, +11.80] | inconclusive → inconclusive | -0.6 [-10.0, +9.1] | -3.6 [-14.6, +4.9] |
| capture-null | +62.9 [+52.3, +74.2] | +38.9 [+24.5, +56.0] | +87.8 [+55.0, +125.0] | +71.1 [+6.5, +140.8] | met → met | -32.12% [-35.46, -28.80] | -22.15% [-29.70, -15.12] | not met → not met | +64.1 [+54.2, +74.5] | +43.3 [+27.1, +63.1] |

#### Attribution, T2 join

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | -1.2 [-11.1, +9.2] | -1.9 [-14.4, +7.1] | -0.6 [-10.0, +9.1] | -3.6 [-14.6, +4.9] |
| capture + construction | `capture-null − wrap-only` | +64.1 [+47.6, +80.2] | +40.8 [+28.9, +54.0] | +64.7 [+48.9, +80.1] | +46.9 [+33.4, +63.0] |
| async enqueue | `http-down − capture-null` | -3.1 [-15.1, +9.3] | +13.8 [-2.8, +27.5] | +13.4 [+1.6, +26.8] | +29.5 [+7.3, +46.8] |
| synchronous file write | `file − http-down` | +24.1 [+19.3, +29.5] | +79.0 [+68.8, +89.7] | +17.9 [+11.1, +25.4] | +70.3 [+56.0, +87.1] |
| SQL comment | `file+sqlcomment − file` | +20.6 [+15.0, +27.2] | +38.6 [+24.6, +52.3] | +22.4 [+18.0, +27.1] | +30.4 [+12.4, +47.4] |

### 4b, T3 insert values

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +90.6 [+49.0, +130.6] | +72.0 [+30.6, +119.7] | +160.0 [-53.3, +370.4] | +185.7 [+82.6, +292.4] | met → met | -16.59% [-23.79, -8.80] | -15.71% [-22.02, -9.27] | not met → not met | +95.2 [+49.0, +139.2] | +83.4 [+46.5, +125.6] |
| http | +118.0 [+68.8, +165.3] | +101.3 [+56.0, +144.7] | +321.1 [+169.1, +451.7] | +319.7 [+225.3, +410.1] | met → met | -21.37% [-28.38, -13.68] | -20.27% [-26.93, -13.48] | not met → not met | +128.2 [+81.3, +172.1] | +114.1 [+72.4, +156.0] |
| http-down | +78.3 [+36.1, +121.2] | +66.8 [+13.3, +118.7] | +137.5 [-91.2, +401.5] | +63.4 [-35.3, +156.8] | met → met | -13.24% [-20.41, -5.33] | -12.55% [-21.13, -3.32] | not met → not met | +76.7 [+33.3, +123.4] | +68.6 [+18.8, +117.7] |
| file+sqlcomment | +149.1 [+103.1, +190.9] | +120.3 [+75.7, +160.2] | +265.6 [+49.4, +508.6] | +221.1 [+88.1, +376.0] | met → met | -24.81% [-32.43, -16.40] | -22.65% [-29.02, -15.16] | not met → not met | +153.1 [+101.1, +201.6] | +131.0 [+86.2, +171.7] |
| wrap-only | -9.1 [-58.6, +50.4] | -19.2 [-64.7, +23.5] | -64.6 [-298.7, +201.7] | -66.8 [-218.1, +92.6] | met → met | +4.87% [-7.12, +16.88] | +7.08% [-4.24, +19.24] | inconclusive → inconclusive | -9.8 [-61.4, +54.7] | -22.4 [-68.6, +22.1] |
| capture-null | +36.3 [-9.8, +76.3] | +42.3 [-43.9, +123.4] | -8.0 [-139.1, +127.7] | +106.4 [-116.3, +391.6] | met → met | -7.10% [-16.34, +3.65] | -6.75% [-22.20, +10.42] | inconclusive → inconclusive | +37.2 [-11.7, +79.6] | +50.5 [-36.1, +137.3] |

#### Attribution, T3 insert values

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | -9.1 [-58.6, +50.4] | -19.2 [-64.7, +23.5] | -9.8 [-61.4, +54.7] | -22.4 [-68.6, +22.1] |
| capture + construction | `capture-null − wrap-only` | +45.4 [-5.9, +91.3] | +61.4 [+6.9, +119.1] | +47.1 [-8.2, +94.9] | +72.8 [+18.5, +133.8] |
| async enqueue | `http-down − capture-null` | +41.9 [-1.8, +87.9] | +24.5 [-42.4, +82.3] | +39.5 [-3.5, +85.9] | +18.1 [-52.7, +77.7] |
| synchronous file write | `file − http-down` | +12.3 [-40.7, +61.2] | +5.2 [-34.5, +43.4] | +18.4 [-40.3, +71.6] | +14.9 [-25.9, +53.1] |
| SQL comment | `file+sqlcomment − file` | +58.6 [+5.7, +108.4] | +48.4 [+7.2, +95.3] | +58.0 [-1.5, +114.3] | +47.6 [+5.6, +95.0] |

### 4b, T4 insert-select

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +131.2 [+92.1, +167.3] | +149.8 [+107.5, +198.9] | +218.8 [+109.1, +327.8] | +254.7 [+121.2, +405.6] | met → met | -23.82% [-29.79, -17.69] | -24.74% [-29.64, -19.78] | not met → not met | +139.7 [+105.6, +172.2] | +152.0 [+110.6, +200.7] |
| http | +147.1 [+105.4, +184.9] | +131.2 [+93.7, +173.4] | +538.1 [+409.1, +666.8] | +606.0 [+378.8, +885.7] | met → met | -27.24% [-33.02, -20.58] | -25.36% [-30.84, -19.58] | not met → not met | +169.8 [+126.8, +207.8] | +154.7 [+111.2, +202.0] |
| http-down | +130.7 [+64.2, +201.7] | +74.4 [+54.3, +92.7] | +373.1 [+126.9, +663.8] | +180.5 [+76.8, +299.6] | met → met | -23.55% [-32.23, -14.56] | -16.12% [-20.08, -11.53] | not met → not met | +150.7 [+83.2, +223.3] | +85.5 [+58.5, +114.3] |
| file+sqlcomment | +198.2 [+140.0, +252.1] | +141.3 [+112.1, +169.1] | +327.4 [+185.0, +463.7] | +264.7 [+158.9, +363.1] | met → met | -31.26% [-38.20, -23.19] | -24.76% [-29.55, -19.68] | not met → not met | +208.1 [+150.8, +260.0] | +144.4 [+114.7, +173.8] |
| wrap-only | +2.3 [-67.0, +70.2] | -11.2 [-48.2, +21.0] | -33.4 [-145.3, +80.8] | -26.6 [-119.6, +51.7] | met → met | +1.59% [-10.83, +15.17] | +2.31% [-5.38, +11.19] | inconclusive → inconclusive | +1.3 [-67.1, +68.6] | -8.8 [-47.4, +24.7] |
| capture-null | +64.3 [+8.3, +121.9] | +84.7 [+23.5, +138.0] | +78.8 [-50.3, +206.6] | +193.9 [+19.1, +359.1] | met → met | -12.77% [-22.94, -2.66] | -14.96% [-24.39, -2.85] | not met → not met | +69.2 [+14.3, +125.5] | +89.1 [+22.5, +146.9] |

#### Attribution, T4 insert-select

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | +2.3 [-67.0, +70.2] | -11.2 [-48.2, +21.0] | +1.3 [-67.1, +68.6] | -8.8 [-47.4, +24.7] |
| capture + construction | `capture-null − wrap-only` | +62.1 [+23.4, +100.3] | +95.9 [+56.6, +140.3] | +67.9 [+25.6, +110.9] | +97.9 [+56.5, +145.8] |
| async enqueue | `http-down − capture-null` | +66.4 [-5.7, +147.0] | -10.3 [-55.5, +36.8] | +81.5 [+4.3, +165.5] | -3.6 [-48.7, +43.5] |
| synchronous file write | `file − http-down` | +0.5 [-59.0, +56.4] | +75.4 [+28.3, +128.1] | -10.9 [-70.9, +48.0] | +66.5 [+20.8, +116.2] |
| SQL comment | `file+sqlcomment − file` | +67.0 [+30.1, +98.5] | -8.5 [-84.4, +57.0] | +68.3 [+28.5, +102.2] | -7.6 [-80.6, +54.8] |

### 4b, T5 analytical

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +99.7 [+86.5, +115.7] | +150.5 [+135.5, +164.8] | +247.0 [+175.1, +318.1] | +390.6 [+258.6, +531.2] | met → met | -36.04% [-39.38, -32.43] | -44.77% [-47.81, -41.67] | not met → not met | +111.0 [+96.0, +126.7] | +159.5 [+143.0, +175.8] |
| http | +69.1 [+59.2, +78.8] | +72.7 [+55.0, +91.9] | +603.2 [+479.2, +705.2] | +520.7 [+372.7, +666.9] | met → met | -32.63% [-34.65, -30.68] | -32.96% [-37.39, -28.35] | not met → not met | +94.2 [+87.3, +100.9] | +97.9 [+80.4, +117.2] |
| http-down | +85.5 [+69.3, +106.1] | +80.3 [+65.0, +98.3] | +192.1 [+123.8, +260.7] | +184.8 [+136.4, +231.6] | met → met | -31.34% [-36.10, -26.84] | -30.36% [-34.94, -26.22] | not met → not met | +91.5 [+73.5, +113.0] | +86.9 [+71.5, +106.1] |
| file+sqlcomment | +113.7 [+101.6, +127.4] | +164.5 [+142.3, +183.5] | +246.9 [+183.3, +312.0] | +224.5 [+169.8, +278.7] | met → met | -39.52% [-42.36, -36.40] | -45.34% [-49.21, -40.96] | not met → not met | +128.1 [+114.0, +142.7] | +164.3 [+142.8, +185.0] |
| wrap-only | +2.4 [-7.9, +14.6] | +16.7 [+0.5, +34.7] | +19.3 [-34.6, +68.7] | +42.6 [-11.3, +94.7] | met → met | -1.22% [-6.39, +3.80] | -8.05% [-15.11, -1.26] | inconclusive → inconclusive | +3.2 [-6.8, +13.9] | +19.2 [+3.5, +36.3] |
| capture-null | +55.3 [+41.7, +73.0] | +56.0 [+44.8, +66.9] | +91.4 [+34.9, +143.1] | +143.6 [+109.4, +179.9] | met → met | -22.37% [-27.89, -17.29] | -25.17% [-29.64, -20.82] | not met → not met | +58.2 [+42.4, +77.3] | +66.8 [+53.4, +81.8] |

#### Attribution, T5 analytical

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | +2.4 [-7.9, +14.6] | +16.7 [+0.5, +34.7] | +3.2 [-6.8, +13.9] | +19.2 [+3.5, +36.3] |
| capture + construction | `capture-null − wrap-only` | +52.9 [+44.0, +62.9] | +39.4 [+24.3, +53.7] | +55.0 [+45.8, +65.9] | +47.6 [+35.7, +58.1] |
| async enqueue | `http-down − capture-null` | +30.2 [+5.2, +56.5] | +24.3 [+8.2, +44.6] | +33.3 [+7.7, +59.0] | +20.1 [+7.6, +33.0] |
| synchronous file write | `file − http-down` | +14.2 [-14.3, +39.3] | +70.1 [+52.9, +84.6] | +19.5 [-6.4, +41.4] | +72.6 [+51.7, +91.5] |
| SQL comment | `file+sqlcomment − file` | +13.9 [-8.9, +34.9] | +14.0 [-10.1, +38.2] | +17.1 [-5.7, +38.8] | +4.8 [-22.0, +31.7] |

### 4b, L1 point read, literal (added in P5.1)

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +408.8 [+394.2, +422.5] | +96.2 [+85.3, +107.9] | +825.0 [+730.7, +921.5] | +197.1 [+143.1, +248.2] | met → met | -75.39% [-76.57, -74.18] | -40.60% [-44.06, -37.27] | not met → not met | +454.5 [+434.2, +474.7] | +103.8 [+92.1, +117.0] |
| http | +449.2 [+432.5, +466.1] | +74.5 [+64.1, +85.2] | +934.5 [+857.3, +1004.8] | +590.8 [+485.3, +715.5] | inconclusive → met | -76.64% [-77.67, -75.50] | -39.54% [-43.15, -35.83] | not met → not met | +486.2 [+467.8, +503.6] | +99.7 [+86.3, +113.4] |
| http-down | +373.5 [+361.9, +389.7] | +57.7 [+48.6, +68.1] | +697.7 [+643.9, +749.3] | +139.9 [+106.5, +177.4] | met → met | -73.24% [-74.01, -72.48] | -30.29% [-33.04, -27.53] | not met → not met | +405.1 [+390.5, +421.9] | +65.7 [+58.1, +73.2] |
| file+sqlcomment | +406.5 [+396.5, +415.0] | +100.9 [+89.0, +112.2] | +811.0 [+704.9, +906.8] | +177.4 [+146.3, +204.1] | met → met | -75.25% [-75.98, -74.38] | -41.64% [-44.91, -38.04] | not met → not met | +449.8 [+435.3, +463.2] | +108.7 [+94.8, +122.2] |
| wrap-only | +6.2 [-3.8, +16.1] | +5.0 [-8.6, +19.5] | +15.2 [-33.8, +54.3] | +15.5 [-37.4, +67.4] | met → met | -2.59% [-8.60, +4.05] | -1.39% [-9.67, +6.91] | inconclusive → inconclusive | +5.0 [-4.9, +14.5] | +4.1 [-9.0, +18.1] |
| capture-null | +364.7 [+351.4, +376.7] | +61.7 [+45.5, +82.3] | +678.6 [+594.2, +759.2] | +138.5 [+84.5, +196.1] | met → met | -73.12% [-74.39, -71.60] | -29.53% [-35.08, -24.52] | not met → not met | +403.9 [+383.0, +422.8] | +65.7 [+50.4, +84.8] |

#### Attribution, L1 point read, literal (added in P5.1)

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | +6.2 [-3.8, +16.1] | +5.0 [-8.6, +19.5] | +5.0 [-4.9, +14.5] | +4.1 [-9.0, +18.1] |
| capture + construction | `capture-null − wrap-only` | +358.5 [+350.2, +367.0] | +56.7 [+38.5, +76.4] | +398.8 [+383.4, +412.5] | +61.5 [+43.4, +81.8] |
| async enqueue | `http-down − capture-null` | +8.8 [-10.6, +29.0] | -3.9 [-17.8, +9.7] | +1.2 [-25.1, +26.9] | +0.0 [-15.7, +14.7] |
| synchronous file write | `file − http-down` | +35.3 [+13.2, +56.1] | +38.4 [+22.3, +53.5] | +49.4 [+21.2, +77.4] | +38.1 [+23.5, +51.9] |
| SQL comment | `file+sqlcomment − file` | -2.3 [-13.2, +6.6] | +4.7 [-5.7, +14.9] | -4.7 [-20.9, +10.6] | +4.9 [-8.1, +17.5] |

### 4b, L3 insert values, literal (added in P5.1)

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +449.4 [+409.2, +492.3] | +97.7 [+59.7, +146.7] | +775.7 [+587.3, +955.4] | +305.0 [+112.3, +503.6] | met → met | -49.83% [-53.15, -46.55] | -19.09% [-27.23, -12.31] | not met → not met | +467.9 [+427.4, +507.8] | +111.7 [+69.4, +163.7] |
| http | +507.8 [+453.2, +563.7] | +127.7 [+77.0, +176.4] | +863.9 [+757.0, +974.0] | +376.5 [+218.6, +584.4] | met → met | -52.50% [-55.03, -50.20] | -23.36% [-31.57, -15.23] | not met → not met | +522.3 [+473.8, +573.1] | +143.9 [+90.4, +199.6] |
| http-down | +432.4 [+391.5, +479.7] | +77.4 [+30.0, +125.0] | +848.6 [+626.2, +1061.8] | +206.9 [+61.6, +371.7] | inconclusive → met | -49.54% [-54.05, -45.08] | -15.36% [-24.03, -6.74] | not met → not met | +463.3 [+420.6, +509.3] | +86.2 [+36.0, +138.2] |
| file+sqlcomment | +479.3 [+436.5, +525.9] | +133.6 [+95.4, +168.4] | +829.7 [+634.1, +1072.0] | +257.6 [+126.7, +385.1] | inconclusive → met | -51.24% [-54.15, -47.92] | -23.36% [-30.04, -16.58] | not met → not met | +493.8 [+458.0, +533.3] | +142.2 [+101.2, +180.4] |
| wrap-only | +15.9 [-46.7, +78.4] | -5.0 [-73.9, +53.3] | -8.6 [-191.5, +177.8] | -8.0 [-200.6, +165.8] | met → met | +0.42% [-11.31, +13.72] | +4.82% [-9.76, +23.31] | inconclusive → inconclusive | +12.0 [-52.3, +74.0] | -6.5 [-81.1, +56.9] |
| capture-null | +399.2 [+344.0, +456.4] | +95.1 [+32.4, +163.2] | +587.2 [+447.5, +733.1] | +230.2 [+75.3, +402.5] | met → met | -46.14% [-51.67, -40.23] | -17.40% [-27.52, -7.21] | not met → not met | +407.4 [+350.9, +464.8] | +105.0 [+41.7, +172.6] |

#### Attribution, L3 insert values, literal (added in P5.1)

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | +15.9 [-46.7, +78.4] | -5.0 [-73.9, +53.3] | +12.0 [-52.3, +74.0] | -6.5 [-81.1, +56.9] |
| capture + construction | `capture-null − wrap-only` | +383.2 [+342.1, +428.9] | +100.1 [+46.3, +150.4] | +395.3 [+354.6, +441.5] | +111.6 [+53.6, +164.2] |
| async enqueue | `http-down − capture-null` | +33.2 [-9.7, +78.1] | -17.7 [-56.8, +18.7] | +55.9 [+10.6, +103.9] | -18.9 [-60.9, +23.4] |
| synchronous file write | `file − http-down` | +17.0 [-35.6, +71.7] | +20.3 [-24.9, +66.0] | +4.6 [-37.5, +50.7] | +25.6 [-22.4, +75.6] |
| SQL comment | `file+sqlcomment − file` | +29.9 [-23.3, +81.8] | +35.9 [-3.6, +77.0] | +25.9 [-22.3, +75.6] | +30.5 [-6.8, +69.8] |

### 4b, L5 analytical, literal (added in P5.1)

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +2841.3 [+2796.9, +2881.8] | +286.1 [+265.6, +306.7] | +6181.5 [+5991.4, +6383.4] | +435.7 [+342.4, +557.7] | not met → met | -85.73% [-86.18, -85.20] | -34.12% [-35.89, -32.41] | not met → not met | +3195.9 [+3141.5, +3248.3] | +284.4 [+265.9, +303.6] |
| http | +3175.5 [+3062.1, +3304.2] | +322.7 [+295.2, +348.4] | +6792.1 [+6420.5, +7171.9] | +652.7 [+573.3, +734.2] | not met → met | -87.01% [-87.47, -86.57] | -37.29% [-39.17, -35.49] | not met → not met | +3571.6 [+3421.5, +3739.3] | +327.1 [+302.9, +350.3] |
| http-down | +2790.8 [+2737.1, +2847.3] | +210.6 [+179.3, +244.4] | +6100.0 [+5854.5, +6351.5] | +322.8 [+208.3, +438.6] | not met → met | -85.68% [-86.11, -85.24] | -27.59% [-30.99, -24.30] | not met → not met | +3184.6 [+3108.4, +3265.1] | +211.8 [+179.8, +245.5] |
| file+sqlcomment | +2882.9 [+2823.7, +2952.2] | +332.7 [+289.0, +379.4] | +6306.9 [+6025.6, +6552.1] | +436.5 [+321.3, +552.5] | not met → met | -86.00% [-86.60, -85.28] | -36.77% [-40.09, -33.57] | not met → not met | +3274.3 [+3184.5, +3375.3] | +324.1 [+281.7, +371.2] |
| wrap-only | +15.2 [-5.0, +35.5] | +19.7 [-11.9, +58.9] | +28.9 [-83.9, +144.2] | +5.0 [-99.0, +118.5] | met → met | -2.28% [-6.31, +1.85] | -2.00% [-7.17, +3.45] | inconclusive → inconclusive | +14.5 [-8.0, +37.2] | +14.2 [-16.3, +44.8] |
| capture-null | +2836.3 [+2806.4, +2866.0] | +209.9 [+166.1, +260.2] | +6177.9 [+5992.4, +6342.6] | +275.2 [+146.7, +415.8] | not met → met | -85.90% [-86.20, -85.54] | -26.66% [-30.72, -22.59] | not met → not met | +3239.7 [+3170.7, +3305.2] | +204.2 [+164.8, +247.0] |

#### Attribution, L5 analytical, literal (added in P5.1)

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | +15.2 [-5.0, +35.5] | +19.7 [-11.9, +58.9] | +14.5 [-8.0, +37.2] | +14.2 [-16.3, +44.8] |
| capture + construction | `capture-null − wrap-only` | +2821.0 [+2797.3, +2847.8] | +190.2 [+163.9, +216.5] | +3225.1 [+3161.7, +3289.2] | +190.0 [+160.7, +219.1] |
| async enqueue | `http-down − capture-null` | -45.4 [-93.1, -1.2] | +0.7 [-59.5, +55.0] | -55.1 [-106.8, -3.3] | +7.7 [-50.4, +58.1] |
| synchronous file write | `file − http-down` | +50.4 [-34.5, +135.3] | +75.5 [+41.0, +108.0] | +11.4 [-101.7, +125.0] | +72.6 [+45.2, +99.8] |
| SQL comment | `file+sqlcomment − file` | +41.6 [-22.3, +111.3] | +46.7 [-6.8, +100.8] | +78.4 [-17.2, +178.7] | +39.7 [-12.1, +92.9] |

### 4b, Kafka `produce()`

| Config | Added p50 µs before | after | Added p99 µs before | after | p99 verdict | Throughput Δ before | after | throughput verdict | Implied µs/call before | after |
|---|---|---|---|---|---|---|---|---|---|---|
| file | +28.4 [+23.1, +35.7] | +48.8 [+46.6, +51.5] | +89.9 [+73.2, +110.1] | +125.3 [+116.1, +134.7] | met → met | -78.67% [-84.68, -72.06] | -87.07% [-91.03, -82.96] | not met → not met | +27.8 [+21.3, +35.4] | +56.1 [+52.2, +60.0] |
| http | +47.6 [+43.5, +50.9] | +43.6 [+37.7, +46.9] | +136.1 [+117.4, +155.6] | +119.4 [+105.7, +132.5] | met → met | -87.99% [-90.81, -84.76] | -81.82% [-87.70, -75.38] | not met → not met | +50.9 [+45.0, +56.3] | +39.5 [+33.1, +44.3] |
| wrap-only | +0.5 [+0.3, +0.6] | +0.6 [+0.3, +0.9] | +2.9 [+0.4, +6.9] | +4.6 [+1.1, +10.2] | met → met | +45.86% [-7.40, +103.48] | +15.86% [-11.04, +44.62] | inconclusive → inconclusive | -1.1 [-3.7, +1.4] | -1.2 [-3.1, +0.5] |
| capture-null | +14.4 [+14.1, +14.7] | +17.2 [+14.8, +20.4] | +51.5 [+48.6, +54.6] | +67.9 [+57.2, +83.7] | met → met | -63.58% [-71.53, -55.10] | -63.27% [-72.86, -53.72] | not met → not met | +11.7 [+10.2, +13.1] | +13.7 [+11.5, +15.9] |

#### Attribution, Kafka `produce()`

| Component | Measured as | p50 µs before | after | Implied µs/call before | after |
|---|---|---|---|---|---|
| wrapper | `wrap-only` | +0.5 [+0.3, +0.6] | +0.6 [+0.3, +0.9] | -1.1 [-3.7, +1.4] | -1.2 [-3.1, +0.5] |
| capture + construction | `capture-null − wrap-only` | +14.0 [+13.6, +14.3] | +16.6 [+14.2, +19.9] | +12.8 [+11.3, +14.3] | +14.9 [+12.9, +17.0] |
| enqueue (http, live backend) | `http − capture-null` | +33.2 [+29.0, +36.4] | +26.4 [+20.4, +31.2] | +39.2 [+33.6, +44.2] | +25.8 [+20.2, +30.6] |
| synchronous file write | `file − capture-null` | +14.0 [+8.8, +21.2] | +31.5 [+27.7, +35.4] | +16.1 [+10.1, +23.3] | +42.4 [+38.7, +46.1] |

### The fixed cost per call and the < 2% throughput target (after)

From the after run's implied added µs per call (point estimate). A fixed cost c per call takes c / (q + c) of the throughput of a query whose own latency is q, so the loss is under 2% once q > 49 × c. The last columns apply each cost to representative query latencies.

| Tier | Config | Implied µs/call [95% CI] | Loss < 2% for queries slower than (µs) | Loss at a 1 ms query | Loss at a 10 ms query | Loss at a 100 ms query |
|---|---|---|---|---|---|---|
| T1 point read | file | +81.8 [+67.9, +96.0] | 4010.1 | 7.56% | 0.81% | 0.08% |
| T1 point read | http | +64.7 [+51.7, +79.5] | 3170.6 | 6.08% | 0.64% | 0.06% |
| T1 point read | http-down | +54.2 [+44.9, +64.2] | 2654.1 | 5.14% | 0.54% | 0.05% |
| T1 point read | file+sqlcomment | +100.0 [+84.5, +115.6] | 4898.3 | 9.09% | 0.99% | 0.10% |
| T2 join | file | +143.1 [+129.3, +156.9] | 7010.5 | 12.52% | 1.41% | 0.14% |
| T2 join | http | +65.4 [+51.9, +77.2] | 3203.4 | 6.14% | 0.65% | 0.07% |
| T2 join | http-down | +72.8 [+56.6, +89.1] | 3567.4 | 6.79% | 0.72% | 0.07% |
| T2 join | file+sqlcomment | +173.4 [+160.4, +186.9] | 8498.1 | 14.78% | 1.70% | 0.17% |
| T3 insert values | file | +83.4 [+46.5, +125.6] | 4088.1 | 7.70% | 0.83% | 0.08% |
| T3 insert values | http | +114.1 [+72.4, +156.0] | 5592.3 | 10.24% | 1.13% | 0.11% |
| T3 insert values | http-down | +68.6 [+18.8, +117.7] | 3359.1 | 6.42% | 0.68% | 0.07% |
| T3 insert values | file+sqlcomment | +131.0 [+86.2, +171.7] | 6419.4 | 11.58% | 1.29% | 0.13% |
| T4 insert-select | file | +152.0 [+110.6, +200.7] | 7448.0 | 13.19% | 1.50% | 0.15% |
| T4 insert-select | http | +154.7 [+111.2, +202.0] | 7580.1 | 13.40% | 1.52% | 0.15% |
| T4 insert-select | http-down | +85.5 [+58.5, +114.3] | 4191.9 | 7.88% | 0.85% | 0.09% |
| T4 insert-select | file+sqlcomment | +144.4 [+114.7, +173.8] | 7077.7 | 12.62% | 1.42% | 0.14% |
| T5 analytical | file | +159.5 [+143.0, +175.8] | 7816.4 | 13.76% | 1.57% | 0.16% |
| T5 analytical | http | +97.9 [+80.4, +117.2] | 4798.1 | 8.92% | 0.97% | 0.10% |
| T5 analytical | http-down | +86.9 [+71.5, +106.1] | 4258.7 | 8.00% | 0.86% | 0.09% |
| T5 analytical | file+sqlcomment | +164.3 [+142.8, +185.0] | 8051.7 | 14.11% | 1.62% | 0.16% |
| L1 point read, literal (added in P5.1) | file | +103.8 [+92.1, +117.0] | 5084.8 | 9.40% | 1.03% | 0.10% |
| L1 point read, literal (added in P5.1) | http | +99.7 [+86.3, +113.4] | 4887.7 | 9.07% | 0.99% | 0.10% |
| L1 point read, literal (added in P5.1) | http-down | +65.7 [+58.1, +73.2] | 3219.6 | 6.17% | 0.65% | 0.07% |
| L1 point read, literal (added in P5.1) | file+sqlcomment | +108.7 [+94.8, +122.2] | 5324.4 | 9.80% | 1.07% | 0.11% |
| L3 insert values, literal (added in P5.1) | file | +111.7 [+69.4, +163.7] | 5474.6 | 10.05% | 1.10% | 0.11% |
| L3 insert values, literal (added in P5.1) | http | +143.9 [+90.4, +199.6] | 7052.1 | 12.58% | 1.42% | 0.14% |
| L3 insert values, literal (added in P5.1) | http-down | +86.2 [+36.0, +138.2] | 4222.3 | 7.93% | 0.85% | 0.09% |
| L3 insert values, literal (added in P5.1) | file+sqlcomment | +142.2 [+101.2, +180.4] | 6968.9 | 12.45% | 1.40% | 0.14% |
| L5 analytical, literal (added in P5.1) | file | +284.4 [+265.9, +303.6] | 13935.6 | 22.14% | 2.77% | 0.28% |
| L5 analytical, literal (added in P5.1) | http | +327.1 [+302.9, +350.3] | 16029.9 | 24.65% | 3.17% | 0.33% |
| L5 analytical, literal (added in P5.1) | http-down | +211.8 [+179.8, +245.5] | 10380.0 | 17.48% | 2.07% | 0.21% |
| L5 analytical, literal (added in P5.1) | file+sqlcomment | +324.1 [+281.7, +371.2] | 15878.7 | 24.47% | 3.14% | 0.32% |
| Kafka `produce()` | file | +56.1 [+52.2, +60.0] | 2747.1 | 5.31% | 0.56% | 0.06% |
| Kafka `produce()` | http | +39.5 [+33.1, +44.3] | 1933.7 | 3.80% | 0.39% | 0.04% |

### Process start-up (ms)

| Command | p50 before | after | p95 before | after |
|---|---|---|---|---|
| python | 13.9 | 15.5 | 19.1 | 20.1 |
| dcp-instrument python | 434.5 | 104.2 | 504.3 | 116.9 |
| python with DCP's sitecustomize | 261.7 | 61.0 | 288.0 | 88.5 |
| python, importing psycopg and confluent_kafka (added in P5.1) | 182.9 | 212.2 | 213.0 | 254.2 |
| dcp-instrument python, importing psycopg and confluent_kafka (added in P5.1) | 446.2 | 264.4 | 476.6 | 323.7 |
