# Single-buffer benchmark results — 2026-10-21

The single-buffer hybrid helps in some configurations, but it is not consistently faster than the better baseline. **All 78 RTL benchmark runs passed**: 20 matched primary triplets plus six supplementary triplets. Each run checks every output word independently. Stage 4 remains unimplemented.

Primary whole-workload outcomes against A-only: **13 wins, 5 ties, 2 losses**. Against B-only: **6 wins, 6 ties, 8 losses**. These are counts of deliberately selected cases, not an estimated win probability. Four cases beat both baselines on whole-workload time; one of those is only a three-cycle startup/phase improvement over B-only and ties its steady throughput. No primary case loses to both simultaneously. The separate aggregate-rate-matched control does lose to both.

Read the [complete tables and configurations](../results/single-buffer-tables.md), [comparison chart](../results/single-buffer-comparison.svg), [flat metrics CSV](../results/single-buffer-metrics.csv), and raw JSON report (development archive). The [measurement contract](single-buffer-benchmark-contract.md) defines all boundaries and counters.

## What was held equal

Within each primary triplet: one logical slot; the same N×32 buffer bits and prefix/suffix bank partition; the same synchronous read/output pipeline; the same ordered address sequence; command availability; both memory-model configurations; and the same reset-relative sink/request-acceptance schedules. Each mode has one outstanding request per used interface. The baselines already support early delivery. Every primary run uses 64 warmup + 1,024 measured blocks, then drains completely.

Hybrid can use two independent memory interfaces, two simultaneous writes and up to two outstanding requests, while each baseline uses one interface and one request. Equal logical storage therefore does **not** mean equal hardware cost or memory bandwidth. There is no shared off-chip contention in these models. The sink accepts at most one word per clock. Empty segments use only their nonempty interface.

Default model: 32-bit beats; N=8,S=3; A latency L=2, interval I=3; B L=6,I=1; burst size K=256 with no gap or cooldown; requests and sink always ready. The nominal long-transfer rates are A=1/3 and B=1 word/cycle. With burst gaps the rate is `1/(I+G/K)`; actual accepted and busy-period rates, request counts and offered/backpressured cycles are recorded for every run. Finite requests do not necessarily achieve that nominal rate.

Whole-workload time below is final consumption minus first command acceptance, in clock intervals. Steady throughput counts the same 1,024 blocks over the window after warmup completion, including all allocation/request/pipeline gaps. Win/tie/loss uses exact integer whole-workload times; steady classification is published separately.

## Representative outcomes

| Configuration | A-only cycles | B-only cycles | Hybrid cycles | Hybrid vs A / B |
| --- | ---: | ---: | ---: | --- |
| Default, N=8,S=3 | 29,375 | 18,495 | 18,495 | win / tie |
| Same memories, S=1 | 29,375 | 18,495 | 17,407 | win / win |
| Same memories, S=7 | 29,375 | 18,495 | 27,199 | win / loss |
| Equal slow memories: both L=2,I=3 | 29,375 | 29,375 | 19,583 | win / win |
| Equal fast memories: both L=2,I=1 | 14,143 | 14,143 | 14,143 | tie / tie |
| Late B: A L=1,I=1; B L=40,I=1 | 13,055 | 55,487 | 52,223 | loss / win |
| Sink ready once every 16 cycles | 139,264 | 139,264 | 139,264 | tie / tie |
| N=32,S=8, default memory timings | 107,711 | 44,607 | 55,487 | win / loss |
| N=256,S=64, default memory timings | 838,847 | 288,319 | 421,055 | win / loss |

Unspecified settings in this table retain the default. Full settings for all 20 primary cases, including bursts/cooldowns, delayed request acceptance, reversed latencies, tiny blocks and S=0/N, are in the generated tables.

**Where hybrid wins.** With S=1, the low-latency A word arrives early without leaving a long slow prefix in front of B's data. Hybrid reaches 0.500000 words/cycle, versus A-only 0.296296 and B-only 0.470588. Its whole-workload baseline/hybrid ratios are 1.6875× and 1.0625×. Equal slow memories give a clearer parallel-bandwidth benefit: hybrid 0.444444 versus 0.296296 for either baseline, a 1.5× steady rate. The burst/cooldown case also beats both (0.173913 versus 0.150943/0.148148), under the explicitly modeled per-request burst boundaries and cooldowns.

**Where it ties.** Default S=3 produces the first word in 5 command-relative cycles versus B-only's 9, but both finish a block at cycle 16 and sustain 8/17 = 0.470588 words/cycle. Earlier first delivery does not guarantee earlier completion. Equal fast memories are limited by the ordered one-word output and common per-block overhead. With the slow sink all three reach exactly 1/16 = 0.0625 words/cycle. Endpoint S=0 is exactly equivalent to B-only; S=N is exactly equivalent to A-only, checked across all recorded metrics.

**Where it loses.** A large slow-A prefix holds up the logically ordered stream even when B has already supplied suffix words. At N=32,S=8, hybrid is 0.627451 versus B-only's 0.780488; at S=24 it falls to 0.385542. The oversized slow-prefix case (N=8,S=7,A I=8,B L=2) is 0.145455 versus B-only's 0.615385. Conversely, when B's startup latency is 40 cycles and A is fast, waiting for any B suffix is costly: hybrid 0.166667 versus A-only 0.666667. Choosing the slower baseline as the only comparator would hide these losses.

**A small whole-time win that does not improve steady throughput.** With A acceptance every 17 cycles and B every 31, hybrid takes 33,740 versus B-only 33,743 cycles. Both sustain 0.258065 words/cycle. Doubling warmup/window to 128+2,048 blocks retains exactly the three-cycle difference (67,468 versus 67,471), with identical steady rates. This is a fixed startup/clock-phase advantage, not a sustained bandwidth gain. Default's doubled window also preserves its steady rates and win/tie classification. These two sensitivity checks are finite checks, not a convergence proof for every timing configuration.

## Controls: early delivery and aggregate rate

`EARLY_DELIVERY=0` waits for full-block commitment before issuing a synchronous bank read. Both controllers expose the same control; default 1 preserves existing behavior. Requests, writes, storage and other protocol rules are unchanged.

| Default N=8,S=3 | A-only cycles | B-only cycles | Hybrid cycles |
| --- | ---: | ---: | ---: |
| Early delivery enabled | 29,375 | 18,495 | 18,495 |
| Full-block-wait control | 36,991 | 26,111 | 22,847 |

Early delivery reduces time in all three default modes. Hybrid's own steady rate rises from 0.380952 to 0.470588 words/cycle. Comparing early hybrid only with a full-block-gated B baseline would manufacture an advantage absent from the fair early/early comparison. With the slow sink, early and gated hybrid tie at 139,264 cycles, while gated A/B take 156,672/156,656: whether early delivery helps depends on when data become ready relative to the sink's fixed readiness schedule.

The **separate aggregate-rate control** uses N=32,S=16,L_A=L_B=2 with no gaps/cooldown. Baselines each use I=1; hybrid uses I_A=I_B=2, giving all modes nominal aggregate service of one word/cycle. Hybrid takes **56,575 cycles versus 40,255 for either baseline**, and sustains **0.615385 versus 0.864865**. It loses to both. Its prefix arrives every other cycle, and ordered delivery prevents early suffix words from filling those prefix gaps. This is a useful bandwidth control, but it changes hybrid's per-interface parameters and still retains its extra interface/concurrency; it is excluded from the matched primary counts.

The two-block startup run takes A/B/hybrid 53/33/33 intervals. It agrees with the default's completion ranking without pretending to be a long steady workload.

## Accounting and independent checks

Default steady useful words are exactly 8,192 in each mode. The windows contain A/B/hybrid 27,648/17,408/17,408 cycles; data-unavailable cycles are 19,456/9,216/9,216 and intentional sink backpressure is zero. Those counts partition each window exactly. Hybrid's maximum committed-minus-consumed backlog is 5 words versus 1/2 for A/B; a held output word is counted once. Default hybrid accepts 1,024 requests per interface versus 1,024 on a baseline's single interface. Full metrics retain averages/maxima, latency min/mean/p95/max, per-interface first/last request/response timing, request skew, offered/accepted/backpressured traffic and busy service rates.

The benchmark monitor uses only public handshakes, with the unchanged address-based scoreboard checking all consumed data independently of the split. Python independently checks window/count identities, deterministic readiness counts, response timing, cooldown and request acceptance, fixed known edge examples and endpoint equivalence. Eight accounting tests include deliberate missing/duplicate record, stall-category, occupancy, busy-cycle and timestamp corruption. Source hashes, fixture hash, simulator/compiler versions, exact configurations, runtime commands and seed policy are saved in raw JSON. Full per-block CSVs and native simulation logs are retained; no failed run contributes a successful result.

## Executed validation and reproduction

All commands below passed from the project root. The benchmark runner rejects missing/failed/stale full correctness reports.

```sh
bash scripts/lint.sh
bash scripts/smoke.sh
bash scripts/test.sh
python3 benchmarks/test_measurements.py
bash scripts/benchmark.sh
python3 benchmarks/report_single_buffer.py
.venv/bin/python benchmarks/plot_single_buffer.py
```

Results: strict lint for five tops; smoke; 36 baseline/model + 32 hybrid regression outcomes; eight measurement tests; 78 benchmark simulations. Shell syntax and Python compilation checks also pass. Matplotlib 3.9.4 was installed into the existing project virtual environment for static charts; the complete resolved environment is pinned in `benchmarks/requirements-plot-lock.txt`. Verilator remains 5.048, Apple Clang 21.0.0, Python 3.9.6. No vendor tool or external service was added.

`bash scripts/benchmark.sh --case default` runs a selected triplet and writes selected-summary.json, not a full-sweep report. `summary.json` and `comparisons.csv` describe the complete 26-triplet sweep. Chart metadata records its input report hash and presentation-script hashes. Preserved checkpoint validation logs are under docs/validation/single-buffer/.

## Limits and next decision

These are deterministic architectural-model results. They establish neither physical DDR behavior nor FPGA frequency, BRAM inference, area, power or board performance. Logical RAM bit equality does not establish equal synthesized resources. The models omit shared external contention and refresh. The sweep samples N=1,8,32,256 and selected splits/timings; it is not an exhaustive optimization or stochastic confidence interval. The gated control is checked on these benchmark workloads, not a separate exhaustive reset campaign. Stage 5's wider randomized/fault campaign remains outstanding.

Recommend retaining S as a parameter and comparing against the better of A-only and B-only. For the original N=8 memory assumptions, S=1 is the best of the splits actually sampled; this is not a universal optimal split. The next architectural checkpoint remains matched two-slot A-only/B-only/hybrid controllers, with two times the logical storage for every mode, FIFO output order and one outstanding request per interface globally. Compare two-slot modes against each other and report one-to-two-slot improvement separately. **Do not implement Stage 4 until the user reviews and approves it.**
