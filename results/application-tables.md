# Finite-tier record analytics: native application results

384 native runs form 96 matched four-way configurations. Each architecture processes identical 128-record query orders, thresholds, release schedules, and readiness patterns. Both stores are finite: B holds 2,048 authoritative words; header A or cache data capacity is 256 words. Header preload is actual B reads and A writes, included in end-to-end cycles. These are exploratory simulation timings, not measured hardware.

The separate correctness campaign passes 40 outcomes: 20 clean cases and 20 named expected failures. Every benchmark result is independently checked by logical record address and fixture values; traffic and cache accounting are re-derived by this report.

## Selected comparisons, including the preload bill

| Workload | Threshold | Timing | Queries | B-only cycles | Eager hybrid cycles | Header-first cycles | Cached B cycles | Fastest |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | --- |
| sequential | 25 | base | 1 | 3667 | 5396 | 3668 | 4223 | b_only |
| sequential | 25 | base | 4 | 14653 | 15956 | 9044 | 16895 | header_first |
| sequential | 25 | a_slow | 1 | 2818 | 3850 | 4885 | 2821 | b_only |
| sequential | 25 | a_slow | 4 | 11265 | 12808 | 17008 | 11269 | b_only |
| sequential | 100 | base | 1 | 3667 | 5396 | 6354 | 4223 | b_only |
| sequential | 100 | base | 4 | 14653 | 15956 | 19796 | 16895 | b_only |
| sequential | 100 | a_slow | 1 | 2818 | 3850 | 6550 | 2821 | b_only |
| sequential | 100 | a_slow | 4 | 11265 | 12808 | 23669 | 11269 | b_only |
| permuted | 25 | base | 1 | 3667 | 5396 | 3668 | 4223 | b_only |
| permuted | 25 | base | 4 | 14653 | 15956 | 9044 | 16895 | header_first |
| permuted | 25 | a_slow | 1 | 2818 | 3850 | 4923 | 2821 | b_only |
| permuted | 25 | a_slow | 4 | 11265 | 12808 | 17166 | 11269 | b_only |
| permuted | 100 | base | 1 | 3667 | 5396 | 6354 | 4223 | b_only |
| permuted | 100 | base | 4 | 14653 | 15956 | 19796 | 16895 | b_only |
| permuted | 100 | a_slow | 1 | 2818 | 3850 | 6550 | 2821 | b_only |
| permuted | 100 | a_slow | 4 | 11265 | 12808 | 23669 | 11269 | b_only |
| hot | 25 | base | 1 | 3667 | 5396 | 3668 | 2423 | cached_b |
| hot | 25 | base | 4 | 14653 | 15956 | 9044 | 9335 | header_first |
| hot | 25 | a_slow | 1 | 2818 | 3850 | 4887 | 2341 | cached_b |
| hot | 25 | a_slow | 4 | 11265 | 12808 | 17035 | 9253 | cached_b |
| hot | 100 | base | 1 | 3667 | 5396 | 6354 | 2423 | cached_b |
| hot | 100 | base | 4 | 14653 | 15956 | 19796 | 9335 | cached_b |
| hot | 100 | a_slow | 1 | 2818 | 3850 | 6550 | 2341 | cached_b |
| hot | 100 | a_slow | 4 | 11265 | 12808 | 23669 | 9253 | cached_b |
| conflict | 25 | base | 1 | 3667 | 5396 | 3668 | 4223 | b_only |
| conflict | 25 | base | 4 | 14653 | 15956 | 9044 | 16895 | header_first |
| conflict | 25 | a_slow | 1 | 2818 | 3850 | 4887 | 2821 | b_only |
| conflict | 25 | a_slow | 4 | 11265 | 12808 | 17035 | 11269 | b_only |
| conflict | 100 | base | 1 | 3667 | 5396 | 6354 | 4223 | b_only |
| conflict | 100 | base | 4 | 14653 | 15956 | 19796 | 16895 | b_only |
| conflict | 100 | a_slow | 1 | 2818 | 3850 | 6550 | 2821 | b_only |
| conflict | 100 | a_slow | 4 | 11265 | 12808 | 23669 | 11269 | b_only |

## Wins, ties and losses against B-only, by experiment family

Each count spans only the four declared thresholds (0/25/50/100) for one workload, timing point and query count. These counts are not probabilities or a cross-workload average. Every column uses cost-inclusive end-to-end cycles.

| Workload | Timing | Queries | Eager hybrid W/T/L | Header-first W/T/L | Cached B W/T/L |
| --- | --- | ---: | --- | --- | --- |
| sequential | base | 1 | 0/0/4 | 1/0/3 | 0/0/4 |
| sequential | base | 4 | 0/0/4 | 3/0/1 | 0/0/4 |
| sequential | b_constrained | 1 | 0/0/4 | 3/0/1 | 0/0/4 |
| sequential | b_constrained | 4 | 0/0/4 | 3/0/1 | 0/0/4 |
| sequential | a_slow | 1 | 0/0/4 | 0/0/4 | 0/0/4 |
| sequential | a_slow | 4 | 0/0/4 | 0/0/4 | 0/0/4 |
| permuted | base | 1 | 0/0/4 | 1/0/3 | 0/0/4 |
| permuted | base | 4 | 0/0/4 | 3/0/1 | 0/0/4 |
| permuted | b_constrained | 1 | 0/0/4 | 3/0/1 | 0/0/4 |
| permuted | b_constrained | 4 | 0/0/4 | 3/0/1 | 0/0/4 |
| permuted | a_slow | 1 | 0/0/4 | 0/0/4 | 0/0/4 |
| permuted | a_slow | 4 | 0/0/4 | 0/0/4 | 0/0/4 |
| hot | base | 1 | 0/0/4 | 1/0/3 | 4/0/0 |
| hot | base | 4 | 0/0/4 | 3/0/1 | 4/0/0 |
| hot | b_constrained | 1 | 0/0/4 | 3/0/1 | 4/0/0 |
| hot | b_constrained | 4 | 0/0/4 | 3/0/1 | 4/0/0 |
| hot | a_slow | 1 | 0/0/4 | 0/0/4 | 4/0/0 |
| hot | a_slow | 4 | 0/0/4 | 0/0/4 | 4/0/0 |
| conflict | base | 1 | 0/0/4 | 1/0/3 | 0/0/4 |
| conflict | base | 4 | 0/0/4 | 3/0/1 | 0/0/4 |
| conflict | b_constrained | 1 | 0/0/4 | 3/0/1 | 0/0/4 |
| conflict | b_constrained | 4 | 0/0/4 | 3/0/1 | 0/0/4 |
| conflict | a_slow | 1 | 0/0/4 | 0/0/4 | 0/0/4 |
| conflict | a_slow | 4 | 0/0/4 | 0/0/4 | 0/0/4 |

## Executed quiescent updates and reload

Four additional native runs first complete a hot query, drain for 20 cycles, perform two authoritative B write handshakes, share reset for three edges, reload headers where applicable, then repeat the query. Word 1 becomes 99 and word 18 becomes 0xffffffff. The result oracle independently detects changed selection and changed selected-record sums. Both epoch ledgers and every phase are retained.

| Architecture | First preload | First query | Writes / cycles | Reset | Second preload | Second query | Total cycles including quiet guard |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| b_only | 0 | 3667 | 2 / 2 | 3 | 0 | 3667 | 7359 |
| hybrid | 1876 | 3520 | 2 / 2 | 3 | 1876 | 3520 | 10817 |
| header_first | 1876 | 2688 | 2 / 2 | 3 | 1876 | 2242 | 8707 |
| cached_b | 0 | 2423 | 2 / 2 | 3 | 0 | 2423 | 4871 |

These writes use the simulation model's one-write-per-cycle load port. This is a quiescent update protocol, not live coherence or a physical write-bandwidth result. See the [predeclared update addendum](../docs/application-update-contract.md).

## How to read the evidence

- `end_to_end_cycles = preload_cycles + query_cycles`. One and four query sequences are actually executed; later-query durations and cache reuse are in the per-run JSON. The separate four-case update experiment includes writes, invalidation and repeat preload; it is not mixed into the 384-run matrix.
- Record i has fixed release edge 2i from query start. Release-to-result tails include host queue waiting. First-offer-to-result and accepted-command-to-result are reported separately because backpressure changes those timestamps. All percentile calculations use nearest rank; the final result edge is included in query duration.
- Hybrid always eagerly fetches 14 payload words per record. Header-first requests a payload only after its key passes. `useless_payload` counts backing-store payload words for records rejected by the fixed predicate. Cache hits avoid a B transaction; its 16 direct-mapped lines deliberately conflict for the conflict workload.
- Header-first is serial and uses fewer assembly resources. Hybrid has two interfaces. The cache has 256 data words plus tags/validity and its own control. Equal data capacity is not equal area, frequency, bandwidth, power, or implementation cost.
- This is a useful predicate-and-sum scan primitive with immutable query epochs, a native user-fixture entrypoint, and quiescent updates. Concurrent updates, coherence, physical memory controllers, real applications beyond this fixed format, synthesis and board measurements remain open.

See [application contract](../docs/application-contract.md), [all run metrics](application-metrics.csv), [all paired comparisons](application-comparisons.csv), and raw evidence (development archive).
