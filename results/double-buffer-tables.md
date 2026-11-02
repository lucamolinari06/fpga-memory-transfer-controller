# Stage 4 matched RTL results

All 2,616 runs pass: 436 configurations × three modes × two buffer capacities. Every depth-one run matches every shared historical per-block field exactly and compares public channels to the original controller each edge. Figures below are simulation cycles and words per cycle under exploratory settings.

## Hybrid against both baselines at equal capacity

| Group | Depth | Cases | H vs A W/T/L | H vs B W/T/L | Beats both |
| --- | ---: | ---: | --- | --- | ---: |
| P0 primary | 1 | 20 | 13/5/2 | 5/7/8 | 3 |
| P0 primary | 2 | 20 | 15/3/2 | 10/4/6 | 8 |
| P1 recommended sequential early-on | 1 | 24 | 0/0/24 | 24/0/0 | 0 |
| P1 recommended sequential early-on | 2 | 24 | 0/0/24 | 24/0/0 | 0 |
| P2 recommended sequential early-on | 1 | 24 | 12/0/12 | 19/0/5 | 8 |
| P2 recommended sequential early-on | 2 | 24 | 12/0/12 | 24/0/0 | 12 |
| P3 recommended sequential early-on | 1 | 24 | 12/0/12 | 19/1/4 | 10 |
| P3 recommended sequential early-on | 2 | 24 | 12/0/12 | 21/2/1 | 12 |

Counts describe sampled cases, not probabilities. Supplementary rate controls, slow sinks, early-off, scattered workloads and window controls remain in the complete comparison CSV and are excluded from this selected table.

## Two slots versus one within each mode

| Profile | Mode | Cases | Faster / tie / slower |
| --- | --- | ---: | --- |
| P0 | A-only | 26 | 22/4/0 |
| P0 | B-only | 26 | 22/4/0 |
| P0 | hybrid | 26 | 21/5/0 |
| P1 | A-only | 126 | 113/13/0 |
| P1 | B-only | 126 | 124/1/1 |
| P1 | hybrid | 126 | 120/6/0 |
| P2 | A-only | 142 | 132/10/0 |
| P2 | B-only | 142 | 141/1/0 |
| P2 | hybrid | 142 | 136/6/0 |
| P3 | A-only | 142 | 134/8/0 |
| P3 | B-only | 142 | 133/4/5 |
| P3 | hybrid | 142 | 133/7/2 |

This comparison explicitly doubles assembly storage from N×32 to 2N×32 data bits for every mode. Interface outstanding limits, memory capacity and shared service limits remain unchanged. Hybrid still has two source interfaces.

## Selected cases

| Case | Depth | A rate | B rate | H rate | H vs A | H vs B |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| default | 1 | 0.296296 | 0.470588 | 0.470588 | win | tie |
| default | 2 | 0.333333 | 0.571429 | 0.727273 | win | win |
| split_1 | 1 | 0.296296 | 0.470588 | 0.500000 | win | win |
| split_1 | 2 | 0.333333 | 0.571429 | 0.615385 | win | win |
| split_7 | 1 | 0.296296 | 0.470588 | 0.320000 | win | loss |
| split_7 | 2 | 0.333333 | 0.571429 | 0.380952 | win | loss |
| late_B | 1 | 0.666667 | 0.156863 | 0.166667 | loss | win |
| late_B | 2 | 0.888889 | 0.166667 | 0.177778 | loss | win |
| oversized_slow_prefix | 1 | 0.129032 | 0.615385 | 0.145455 | win | loss |
| oversized_slow_prefix | 2 | 0.135593 | 0.800000 | 0.156863 | win | loss |
| slow_sink | 1 | 0.062500 | 0.062500 | 0.062500 | tie | tie |
| slow_sink | 2 | 0.062500 | 0.062500 | 0.062500 | tie | tie |
| aggregate_rate_control | 1 | 0.864865 | 0.864865 | 0.615385 | loss | loss |
| aggregate_rate_control | 2 | 0.941176 | 0.941176 | 0.969697 | win | win |
| path_p1_n8_s3_sequential_seed11_early1 | 1 | 0.572667 | 0.128074 | 0.133996 | loss | win |
| path_p1_n8_s3_sequential_seed11_early1 | 2 | 0.727725 | 0.133996 | 0.141801 | loss | win |
| path_p1_n32_s8_sequential_seed11_early1 | 1 | 0.842452 | 0.349410 | 0.382759 | loss | win |
| path_p1_n32_s8_sequential_seed11_early1 | 2 | 0.914082 | 0.361658 | 0.397366 | loss | win |
| path_p1_n256_s64_sequential_seed11_early1 | 1 | 0.977092 | 0.702336 | 0.874892 | loss | win |
| path_p1_n256_s64_sequential_seed11_early1 | 2 | 0.988380 | 0.708071 | 0.883821 | loss | win |
| path_p2_n8_s3_sequential_seed11_early1 | 1 | 0.274992 | 0.124514 | 0.129126 | loss | win |
| path_p2_n8_s3_sequential_seed11_early1 | 2 | 0.307196 | 0.127444 | 0.137061 | loss | win |
| path_p2_n32_s8_sequential_seed11_early1 | 1 | 0.316764 | 0.343740 | 0.375010 | win | win |
| path_p2_n32_s8_sequential_seed11_early1 | 2 | 0.326352 | 0.357425 | 0.379435 | win | win |
| path_p2_n256_s64_sequential_seed11_early1 | 1 | 0.331194 | 0.666660 | 0.658200 | win | loss |
| path_p2_n256_s64_sequential_seed11_early1 | 2 | 0.332467 | 0.666662 | 0.844708 | win | win |
| path_p3_n8_s3_sequential_seed11_early1 | 1 | 0.249992 | 0.123301 | 0.125000 | loss | win |
| path_p3_n8_s3_sequential_seed11_early1 | 2 | 0.270015 | 0.125000 | 0.125857 | loss | win |
| path_p3_n32_s8_sequential_seed11_early1 | 1 | 0.278079 | 0.328153 | 0.362976 | win | win |
| path_p3_n32_s8_sequential_seed11_early1 | 2 | 0.286009 | 0.339013 | 0.375126 | win | win |
| path_p3_n256_s64_sequential_seed11_early1 | 1 | 0.289920 | 0.611914 | 0.608187 | win | loss |
| path_p3_n256_s64_sequential_seed11_early1 | 2 | 0.290956 | 0.624987 | 0.675911 | win | win |

## Early-delivery controls

| Profile | Depth | Paired mode/configurations | Early on faster / tie / slower |
| --- | ---: | ---: | --- |
| P0 | 1 | 6 | 5/1/0 |
| P0 | 2 | 6 | 0/6/0 |
| P1 | 1 | 156 | 153/3/0 |
| P1 | 2 | 156 | 0/156/0 |
| P2 | 1 | 180 | 180/0/0 |
| P2 | 2 | 180 | 0/180/0 |
| P3 | 1 | 180 | 180/0/0 |
| P3 | 2 | 180 | 10/163/7 |

Each pair has identical memory settings, input files and capacity. Counts combine separately labeled modes/configurations only to describe these controls; consult the CSV for each baseline and split. Phase-dependent changes in admission can make early-on slower in a finite window.


## Window sensitivity

3 hybrid-versus-baseline classifications change between the paired standard and doubled windows (both depths counted). Treat these as phase/window-sensitive comparisons.

- path_p3_n8_s3_sequential_seed29_early1_long, depth 1, vs B: loss → win.
- path_p3_n8_s3_conflict_seed29_early1_long, depth 2, vs B: win → loss.
- path_p3_n8_s3_conflict_seed29_early0_long, depth 2, vs B: win → loss.
