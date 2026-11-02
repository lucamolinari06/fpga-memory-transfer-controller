# Single-buffer benchmark checkpoint contract

Each primary triplet uses the same N, S, N×32 logical buffer bits, synchronous banks, elastic output, one slot, workload, reset, memory A/B settings, sink schedule and immediate command availability. A baseline uses one full-block request on its selected interface; hybrid uses independent prefix/suffix requests. Both baselines already deliver early. Empty hybrid segments issue no request. Hybrid's two interfaces and up to two outstanding requests are extra resources, even when the logical storage is equal.

The only RTL addition is `EARLY_DELIVERY`, default 1, on both controllers. Setting it to 0 adds a full-block-committed condition to read issue. Request issue, writes, storage and output holding are unchanged. The control still observes the same synchronous read delay: earliest consumption is two edges after the final arrival. The primary results all use the original early delivery behavior. This parameter is an experiment, not a replacement for committed-count validity.

`benchmark_tb.sv` elaborates exactly one controller per executable. It shares the existing memory, sink and independent address-scoreboard modules. No internal DUT signal supplies benchmark measurements. Public handshakes track requests, response ownership and timestamps, consumption, slot ownership, and committed-minus-consumed backlog. Every word is independently checked from its command address; a checksum is an additional end check. A 20-cycle quiet drain rejects extra output. Native simulation uses assertions and strict warnings, with 10 million simulated cycles and a 60-second run limit.

The driver repeats 128 aligned blocks at bases `256 + (j % 128)*N`, including at N=256 within the 65,536-word fixture. All modes see the same ordered sequence and hold commands until accepted. Repetition does not create cache hits: neither model contains a cache. Three shared reset clock edges precede release. Edge 0 is the first rising edge after release; command 0 must accept there. No reset occurs during measurement. Sink readiness depends on reset-relative clock, never DUT validity. Memory request acceptance also follows a fixed clock schedule; burst gaps and cooldown depend on their documented request/response events.

Primary runs: 64 warmup blocks plus 1,024 measured blocks, then drain. Secondary runs include a two-block startup case and 128+2,048-block sensitivity checks. All are deterministic (`randomized=false`, `seed=null`). No randomness claim or arbitrary favorable seed selection.

Per-block CSV rows contain c (command), per-interface accepted-request edges, first/last response edges, f (first consumption), d (last consumption), and cumulative counters including edge d. An absent interface uses timestamp -1. The last row minus the warmup boundary row yields exactly the open-left/closed-right steady window `(d_63,d_1087]`. The whole category window is `[c_0,d_1087]`, inclusive; whole-workload latency is `d_1087-c_0`, in intervals. Initial command acceptance is checked at edge 0, so reset-release-to-last and whole latency coincide. The drain tail is excluded.

- Throughput: measured words / steady window cycles, including every inter-block gap.
- First-word and completion latency: f−c and d−c; also f−first request and d−first request. Report mean/min/p95/max over measured blocks, and per-block request acceptance skew.
- Cycle partition: useful = valid & ready; unavailable = ready & !valid; intentional = !ready. Held = valid & !ready is a subset of intentional, not another disjoint category.
- Post-edge slot occupancy is 1 after command acceptance, 0 after final consumption. Backlog is accepted responses minus consumed words, including held output exactly once. Average and maximum are recorded for whole/steady windows; maximum slot capacity is 1 and backlog capacity N.
- Per interface: accepted requests/beats, offered-valid cycles, response-backpressured cycles, and outstanding-busy cycles. Busy uses pre-edge ownership, covering `(accepted request, final response]`; accepted beats/window and accepted beats/busy cycles have different denominators.
- Long-transfer nominal service rate is `1/(I+G/K)` words/cycle; finite request rate also includes initial latency, request length, and boundary effects. Measured interface rates are retained separately. Sink peak is one word/cycle.

Python validates CSV completeness, exact counts, monotonic cumulative counters, category identities, independently counted clock-schedule readiness, request mapping/timing, cooldown/acceptance, busy intervals, backlog limits, fixed hand-derived timing examples, and exact endpoint equivalence. It does not generate the expected data via the split algorithm. Existing 36-case baseline/model and 32-case hybrid regressions must pass for the exact hashed sources before benchmarks run. The benchmark runner rejects stale reports. Failed/time-out runs abort the sweep and cannot produce a successful comparison file.

Classification uses exact whole-workload intervals: fewer = win, equal = tie, more = loss, against each baseline separately. Also publish steady classifications, because finite clock-phase effects can differ. Speed ratio = baseline whole intervals / hybrid whole intervals; above 1 favors hybrid. No rounding tolerance decides ties. The selected cases are directed examples, not a probability distribution; win counts cannot be generalized to arbitrary workloads.

Supplementary controls are separated from the primary table:

1. Full-block-wait control (`EARLY_DELIVERY=0`) for all three modes in default and slow-consumer settings. Same memory resources/settings as each early-enabled counterpart.
2. Aggregate-rate control: N=32,S=16,L_A=L_B=2,G=C=0; baselines I=1, hybrid I_A=I_B=2. Nominal aggregate service is one word/cycle for each mode, but two-interface hardware and concurrency remain different. This changes hybrid timing and is not part of the identical-memory-settings primary matrix.
3. Short workload and doubled warmup/window checks, reported separately.

No synthesized BRAM count, clock rate, physical DDR behavior, energy, area, double-buffer gain or hardware speedup is inferred from these architectural cycles.
