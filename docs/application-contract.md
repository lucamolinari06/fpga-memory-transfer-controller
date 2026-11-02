# Finite-tier record analytics experiment — 2026-11-02

The user explicitly requested revisiting prior ideas, expanding beyond the roadmap to something useful, and implementing as far as possible. The selected experiment advances the user's unified heterogeneous-memory idea with one logical record address space, finite physical placement, and a real predicate/sum consumer. This authorizes this simulation experiment after the core consolidation; it does not claim the user reviewed its implementation. Hardware, coherence, a CPU bus, runtime policy selection, and extra memory outstanding requests are not introduced.

## Fixed application and alternatives (declared before runs)

There are 128 immutable records of 16 unsigned 32-bit words. Logical word `16*r+0` is a unique record ID, word 1 is a key in 0..99, and words 2..15 are payload samples. A query selects `key < threshold` and computes the exact unsigned 64-bit sum of each selected record's 14 samples. Every submitted record produces one ordered result `{id, selected, sum}`; a rejected record has sum zero. An independent fixture/address-based reference checks all three fields, including rejected records. This is an analytical scan primitive, not a complete database or packet stack.

Memory B holds the complete 2,048-word (8 KiB) authoritative dataset. In header-placement modes, Memory A holds only the packed two-word headers: physical `2*r + offset` for logical `16*r + offset`, offset 0/1. A has 256 words (1 KiB), and cannot serve payloads. A request crossing a header or beyond the dataset fails. Both interfaces allow one outstanding request, ordered stable response beats, and fixed per-run exploratory latency/interval controls. No real memory technology ordering is presumed.

Compare four separately labeled designs:

1. `b_only`: unchanged common controller, B-only, two assembly slots, early delivery.
2. `hybrid`: unchanged common controller, two slots, S=2, eager concurrent A headers/B payloads. It fetches payloads even for rejected records.
3. `header_first`: serial conventional header-first scheduler; A fetches the two header words, then B fetches 14 payload words only if selected. It emits a short rejected stream ending at word 1. It uses fewer assembly resources, so it is a conditional-fetch control, not an equal-cost copy of hybrid.
4. `cached_b`: the same two-slot B-only core backed by a synthesizable direct-mapped whole-record cache: 16 lines × 16 words = 256 data words (1 KiB), plus tags/validity. This matches A's data capacity, not exact physical area. A miss fetches the full B record; cold/working-set/conflict effects and refill traffic are measured.

The consumer is shared by all four designs and exposes ready/valid results. It accepts a full 16-word record, or a two-word rejected record only. Result stalls stop input when the result holding register is occupied. Input, memory requests/responses and results hold payloads stable under stalls. The 64-bit sum cannot overflow for this fixed record format. Query threshold remains fixed within an epoch.

## Preload, reuse, updates, and metrics

Header modes start with an empty A. Before any application commands, actual B transactions read each record's two header words and handshake writes into packed A. Record the elapsed preload cycles and words; the stream cannot begin before this barrier. Other modes start cold with zero preload. Do not hide this cost in the main end-to-end number. Report steady query execution separately and cost-inclusive `preload + queries` for 1 and repeated queries. All modes use identical query orders and output-ready schedules measured from query workload start; preload is a separate phase.

The dataset is immutable during each epoch. A quiescent update/reload experiment, if implemented, must drain all work, change the authoritative fixture, invalidate cache/header state, and repeat measured preload before queries. Until that experiment exists, update bandwidth/consistency remain an explicitly unimplemented limitation; derived reload amortization is a cost scenario, not an executed update engine.

Predeclared workloads: sequential scan; recorded-seed permutation; hot eight-record working set; cache-conflicting addresses. Thresholds 0/25/50/100, including no matches/all matches. Timing points: A latency 2/interval 1 and B 12/1; B constrained to interval 3; reverse-favorable A 20/2 and B 4/1. Fixed request/consumer stalls are independent of DUT valid. Report completed queries/records, selected results, end-to-end cycles, per-record completion mean/p95/p99/max, A/B transferred words, useless eager payload words, preload cost and cache hit/miss/refill counts. No universal average across unlike cases.

Native directed verification precedes performance: backpressure, no/all matches, bounded addresses, shared reset/cancel, same-capacity cache collisions and hits, and deliberate result-data/selection/ID/drop faults matched to named diagnostics. Every performance configuration is independently scored; logs, fixture/schedule/source hashes, exact argv and recorded seeds are retained separately under `results/raw/application/`. New application RTL/models/runners do not modify core evidence or prior controllers.

## Module boundaries

- `record_reduce`: `clk,rst,threshold[31:0]`; `in_valid,in_ready,in_data[31:0],in_last`; `result_valid,result_ready,result_id[31:0],result_selected,result_sum[63:0]`.
- `header_first_controller`: the existing common controller's `cmd_*`, `a_req/rsp_*`, `b_req/rsp_*`, and `out_*` ports, plus `threshold[31:0]`. Fixed 16-word records, two header words. Serial command ownership through the final stream handshake.
- `record_cache`: `clk,rst`; front `req_valid,req_ready,req_base_word[31:0],req_words[8:0],rsp_valid,rsp_ready,rsp_data[31:0],rsp_last`; backend uses identical names with `mem_` prefix. Fixed aligned full-record requests; synchronous cache hit reads, write-on-miss, stable registered output, valid only after the complete fill; reset invalidates all lines and must also reset backend/controller/scoreboard. Optional public counters `hit_count,miss_count` are 32 bits. No coherence, writeback, bypass policy selection, or multiple misses.

Keep all synthesizable logic under `rtl/`, behavioral storage under `sim/models/`, and native stimulus/scoring under `sim/tb/`. A standard-library host runner generates fixtures and expected values but never substitutes for RTL execution.
