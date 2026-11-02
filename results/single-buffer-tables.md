# Executed single-buffer benchmark tables

Generated from `raw/single_buffer/summary.json`; all measurements are architectural cycles or 32-bit words/cycle. Full per-block CSVs and run logs are under `raw/single_buffer/`.

## Matched primary configurations

Defaults: N=8,S=3; A: L=2,I=3,K=256,G=0,C=0, acceptance=1/1; B: L=6,I=1,K=256,G=0,C=0, acceptance=1/1. Sink=1/1 ready, no fixed stall. Every row uses 64 warmup + 1,024 measured blocks, early delivery enabled, one slot. L/I/G/C are cycles; K is words. All three modes within a row receive the same full configuration.

| Case | N | S | Changes from default |
| --- | --- | --- | --- |
| default | 8 | 3 | none |
| equal_fast | 8 | 3 | a_interval=1, b_latency=2 |
| equal_slow | 8 | 3 | b_latency=2, b_interval=3 |
| reversed_latency | 8 | 3 | a_latency=12, b_latency=2 |
| slow_A | 8 | 3 | a_interval=8, b_latency=2 |
| late_B | 8 | 3 | a_latency=1, a_interval=1, b_latency=40 |
| slow_sink | 8 | 3 | sink_period=16 |
| bursts_cooldown | 8 | 3 | a_burst=2, a_gap=4, a_cooldown=17, b_burst=2, b_gap=5, b_cooldown=25 |
| request_skew | 8 | 3 | a_accept_period=17, b_accept_period=31 |
| split_0 | 8 | 0 | none |
| split_1 | 8 | 1 | none |
| split_7 | 8 | 7 | none |
| split_8 | 8 | 8 | none |
| tiny_B | 1 | 0 | none |
| tiny_A | 1 | 1 | none |
| large_prefix8 | 32 | 8 | none |
| large_prefix24 | 32 | 24 | none |
| maximum_block | 256 | 64 | none |
| equal_balanced | 32 | 16 | a_interval=1, b_latency=2 |
| oversized_slow_prefix | 8 | 7 | a_interval=8, b_latency=2 |


## Whole workload: exact win/tie/loss

Elapsed intervals from first command to final consumption, including all 1,088 blocks. Ratio is baseline/hybrid; >1 favors hybrid. Classifications use exact integers, not rounded ratios.

| Case | A cycles | B cycles | Hybrid cycles | H vs A | H vs B | A/H | B/H |
| --- | --- | --- | --- | --- | --- | --- | --- |
| default | 29375 | 18495 | 18495 | win | tie | 1.5883 | 1.0000 |
| equal_fast | 14143 | 14143 | 14143 | tie | tie | 1.0000 | 1.0000 |
| equal_slow | 29375 | 29375 | 19583 | win | win | 1.5000 | 1.5000 |
| reversed_latency | 40255 | 14143 | 29375 | win | loss | 1.3704 | 0.4815 |
| slow_A | 67455 | 14143 | 29375 | win | loss | 2.2963 | 0.4815 |
| late_B | 13055 | 55487 | 52223 | loss | win | 0.2500 | 1.0625 |
| slow_sink | 139264 | 139264 | 139264 | tie | tie | 1.0000 | 1.0000 |
| bursts_cooldown | 57649 | 58729 | 50025 | win | win | 1.1524 | 1.1740 |
| request_skew | 37000 | 33743 | 33740 | win | win | 1.0966 | 1.0001 |
| split_0 | 29375 | 18495 | 18495 | win | tie | 1.5883 | 1.0000 |
| split_1 | 29375 | 18495 | 17407 | win | win | 1.6875 | 1.0625 |
| split_7 | 29375 | 18495 | 27199 | win | loss | 1.0800 | 0.6800 |
| split_8 | 29375 | 18495 | 29375 | tie | loss | 1.0000 | 0.6296 |
| tiny_B | 6527 | 10879 | 10879 | loss | tie | 0.6000 | 1.0000 |
| tiny_A | 6527 | 10879 | 6527 | tie | win | 1.0000 | 1.6668 |
| large_prefix8 | 107711 | 44607 | 55487 | win | loss | 1.9412 | 0.8039 |
| large_prefix24 | 107711 | 44607 | 90303 | win | loss | 1.1928 | 0.4940 |
| maximum_block | 838847 | 288319 | 421055 | win | loss | 1.9923 | 0.6848 |
| equal_balanced | 40255 | 40255 | 40255 | tie | tie | 1.0000 | 1.0000 |
| oversized_slow_prefix | 67455 | 14143 | 59839 | win | loss | 1.1273 | 0.2364 |


Directed-case totals (not probabilities): `{"A": {"loss": 2, "tie": 5, "win": 13}, "B": {"loss": 8, "tie": 6, "win": 6}}`.

## Steady throughput

Each mode uses its own completion-delimited window `(d_63,d_1087]` for the same measured work. Sink/request readiness still follows the same reset-relative clock. All gaps are counted.

| Case | A words/cycle | B words/cycle | Hybrid words/cycle | Steady H vs A | Steady H vs B |
| --- | --- | --- | --- | --- | --- |
| default | 0.296296 | 0.470588 | 0.470588 | win | tie |
| equal_fast | 0.615385 | 0.615385 | 0.615385 | tie | tie |
| equal_slow | 0.296296 | 0.296296 | 0.444444 | win | win |
| reversed_latency | 0.216216 | 0.615385 | 0.296296 | win | loss |
| slow_A | 0.129032 | 0.615385 | 0.296296 | win | loss |
| late_B | 0.666667 | 0.156863 | 0.166667 | loss | win |
| slow_sink | 0.062500 | 0.062500 | 0.062500 | tie | tie |
| bursts_cooldown | 0.150943 | 0.148148 | 0.173913 | win | win |
| request_skew | 0.235294 | 0.258065 | 0.258065 | win | tie |
| split_0 | 0.296296 | 0.470588 | 0.470588 | win | tie |
| split_1 | 0.296296 | 0.470588 | 0.500000 | win | win |
| split_7 | 0.296296 | 0.470588 | 0.320000 | win | loss |
| split_8 | 0.296296 | 0.470588 | 0.296296 | tie | loss |
| tiny_B | 0.166667 | 0.100000 | 0.100000 | loss | tie |
| tiny_A | 0.166667 | 0.100000 | 0.166667 | tie | win |
| large_prefix8 | 0.323232 | 0.780488 | 0.627451 | win | loss |
| large_prefix24 | 0.323232 | 0.780488 | 0.385542 | win | loss |
| maximum_block | 0.332036 | 0.966038 | 0.661499 | win | loss |
| equal_balanced | 0.864865 | 0.864865 | 0.864865 | tie | tie |
| oversized_slow_prefix | 0.129032 | 0.615385 | 0.145455 | win | loss |


## First-word latency

Mean command-to-first-consumption intervals over the 1,024 measured blocks. Min/p95/max and request-based metrics remain in the JSON/flat CSV.

| Case | A first | B first | Hybrid first |
| --- | --- | --- | --- |
| default | 5.000 | 9.000 | 5.000 |
| equal_fast | 5.000 | 5.000 | 5.000 |
| equal_slow | 5.000 | 5.000 | 5.000 |
| reversed_latency | 15.000 | 5.000 | 15.000 |
| slow_A | 5.000 | 5.000 | 5.000 |
| late_B | 4.000 | 43.000 | 4.000 |
| slow_sink | 15.000 | 15.000 | 15.000 |
| bursts_cooldown | 19.000 | 31.000 | 5.000 |
| request_skew | 12.000 | 23.000 | 12.825 |
| split_0 | 5.000 | 9.000 | 9.000 |
| split_1 | 5.000 | 9.000 | 5.000 |
| split_7 | 5.000 | 9.000 | 5.000 |
| split_8 | 5.000 | 9.000 | 5.000 |
| tiny_B | 5.000 | 9.000 | 9.000 |
| tiny_A | 5.000 | 9.000 | 5.000 |
| large_prefix8 | 5.000 | 9.000 | 5.000 |
| large_prefix24 | 5.000 | 9.000 | 5.000 |
| maximum_block | 5.000 | 9.000 | 5.000 |
| equal_balanced | 5.000 | 5.000 | 5.000 |
| oversized_slow_prefix | 5.000 | 5.000 | 5.000 |


## Separate controls

Gated rows use EARLY_DELIVERY=0 in all three modes; default_gated and slow_sink_gated otherwise match their primary namesakes. Aggregate-rate control uses N=32,S=16,L_A=L_B=2,G=C=0: baselines I=1, hybrid I_A=I_B=2. It changes hybrid memory settings and is deliberately excluded from primary win totals. Short_default uses 1 warmup + 1 measured block. Long_window cases use 128+2,048 blocks.

| Case | Group | A cycles | B cycles | H cycles | H vs A | H vs B | A rate | B rate | H rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| default_gated | ablation | 36991 | 26111 | 22847 | win | win | 0.235294 | 0.333333 | 0.380952 |
| slow_sink_gated | ablation | 156672 | 156656 | 139264 | win | win | 0.055556 | 0.055556 | 0.062500 |
| aggregate_rate_control | rate_control | 40255 | 40255 | 56575 | loss | loss | 0.864865 | 0.864865 | 0.615385 |
| short_default | short | 53 | 33 | 33 | win | tie | 0.296296 | 0.470588 | 0.470588 |
| default_long_window | sensitivity | 58751 | 36991 | 36991 | win | tie | 0.296296 | 0.470588 | 0.470588 |
| request_skew_long_window | sensitivity | 73992 | 67471 | 67468 | win | win | 0.235294 | 0.258065 | 0.258065 |


## Default steady counters and occupancy

| Metric | A-only | B-only | Hybrid |
| --- | --- | --- | --- |
| cycles | 27648 | 17408 | 17408 |
| useful | 8192 | 8192 | 8192 |
| unavailable | 19456 | 9216 | 9216 |
| intentional | 0 | 0 | 0 |
| held | 0 | 0 | 0 |
| slot_average | 0.9629629629629629 | 0.9411764705882353 | 0.9411764705882353 |
| slot_max | 1 | 1 | 1 |
| backlog_average | 0.5925925925925926 | 0.9411764705882353 | 1.8235294117647058 |
| backlog_max | 1 | 2 | 5 |
| early_words | 7168 | 5120 | 2048 |
| a_requests | 1024 | 0 | 1024 |
| b_requests | 0 | 1024 | 1024 |
| a_beats | 8192 | 0 | 3072 |
| b_beats | 0 | 8192 | 5120 |
| a_accepted_rate | 0.2962962962962963 | 0.0 | 0.17647058823529413 |
| b_accepted_rate | 0.0 | 0.47058823529411764 | 0.29411764705882354 |
| a_busy_service_rate | 0.34782608695652173 | 0 | 0.375 |
| b_busy_service_rate | 0 | 0.6153846153846154 | 0.5 |

