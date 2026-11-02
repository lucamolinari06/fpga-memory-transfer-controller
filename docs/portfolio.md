# Engineering case study: split-memory streaming

This project asks when fetching a block's prefix from Memory A and its suffix from Memory B helps an ordered consumer. The controller is SystemVerilog, verification executes native RTL, and comparisons include both single-memory alternatives with the same assembly-buffer depth. The [core evaluation](stage6-results.md) consolidates that evidence; the separate [application report](application-results.md) measures useful computation with finite data placement.

## Design decisions

| Decision | Reason and consequence |
| --- | --- |
| Common core across modes and depths | Makes allocator, banks and reader comparable. Hybrid still has two source interfaces. |
| One outstanding request per interface | Ordered responses need one owner per interface rather than external IDs. Limits memory parallelism. |
| Separate prefix/suffix banks per slot | Allows concurrent A/B writes and synchronous reading with one write and one read port per bank. Physical mapping remains unmeasured. |
| Committed-prefix counts | Permits early consumption without a full-block gate. Requires contiguous, ordered responses. |
| Head-only synchronous reading | Preserves order; a write at `w` can first be consumed at `w+2`. Retains an explicit inter-block bubble. |
| Stable pending descriptors and accepted owners | Keeps requests and responses attached to their slot even as the FIFO head changes. |
| Shared cancellation reset | Clears validity and ownership across the entire simulation epoch. Controller-only reset with live external responses is unsupported. |

Assembly data storage is `BUFFER_COUNT × N × 32` bits, plus bank output registers and control metadata. Banks are not reset. Their registered output supplies the held stream data; there is no extra unconditional shared data register. See the [contract](stage4-contract.md) and [RTL](../rtl/buffered_transfer_controller.sv).

## A cycle walkthrough

The executed two-slot, eight-word example consumes block 0 at edges **5, 8, 11, 12, 13, 14, 15, 16**, and block 1 at **18, 19, 20, 21, 22, 23, 24, 25**. Edge 17 is the deliberate boundary bubble.

A accepts block 1's prefix at edge 10 while B still owns block 0. B accepts block 1's suffix at edge 12. Each interface therefore needs an independent owner; routing responses using the current head would be wrong. Reading remains restricted to the head even when the next slot has committed data.

During output backpressure, the selected RAM output, bank selection, `last` and `valid` remain stable. A final word that has been fetched but not consumed still owns its slot. Only the final output handshake can retire it. The [Stage 4 report](stage4-results.md) connects these rules to actual native checks and measurement accounting.

## A checker that can disagree with the design

The [scoreboard](../sim/tb/address_scoreboard.sv) sees accepted commands and output words. It queues logical addresses and independently derives fixture values. It has no split parameter, bank address, memory-response input or DUT validity counter. Wrong routing cannot redefine the expected answer.

Stage 4 records **229 native outcomes**: 216 positives and 13 named expected failures. Stage 5 adds **232**: 192 clean stress configurations, 24 resets and eight matched clean/fault pairs. Recorded finite schedules control command offers, sink readiness, request admission and response release independently of DUT output validity.

Faults include a flipped bit, duplication, adjacent reordering, middle/final drops, early/late `last` and extra output. Each must produce its intended diagnostic. A middle drop shifts subsequent addresses; a final drop needs a bounded pending-address check because no later word reveals the error. An unrelated timeout or compile failure never counts as a successful negative test.

This is finite simulation, not formal proof or a coverage percentage. The seeded cross-product covers P0/P3, two geometries and four seed/workload schedules. Other profile and reset witnesses come from distinct directed suites. [Stage 5 results](stage5-results.md) records both the observations and gaps.

## Comparison discipline

The benchmark contains **436 configurations × three modes × two depths = 2,616 native runs**, checking **98,755,968 output words**. All **1,308 depth-one record sets** match historical shared fields. Source, fixture, trace and record hashes bind evidence to inputs.

Matched sets keep workloads, sink schedules, memory settings and disturbance traces fixed. Each baseline issues one full-block request, avoiding an artificial double latency charge. Both baselines receive the same extra assembly storage at depth two. The aggregate-rate control changes service settings and stays separate from primary counts.

A window may consume prefetched data received before its start. Accounting includes stored backlog and held output; it does not assume equal response/consumption counts within the window. Python orchestrates native runs and reports metrics; no Python controller model replaces RTL execution. Four traces are repeatable schedules, not confidence intervals.

## Findings that survive scrutiny

Default P0 N=8,S=3 at depth two yields A/B/hybrid rates **0.333333 / 0.571429 / 0.727273 words/cycle**: a **27.3% hybrid gain over B** in that specific comparison. At one slot, hybrid and B tie at 0.470588. This is a simulation result with unequal interface resources, not an equal-cost hardware speedup.

The strong alternative matters: full-rate A wins all 24 recommended quiet P1 sequential cases at either depth. Recommended two-slot P2 and P3 hybrid beats both baselines in 12 of 24 cases each. Poor splits and slow consumers still lose or tie.

Throughput and latency differ. Default P0 hybrid's mean command-to-first latency rises from 5 to 12 cycles at depth two because admission occurs earlier and includes more queue waiting. In P2 N=32,S=8, trace 11, two-slot hybrid improves mean completion and rate over both baselines, yet its completion p99 is 215 cycles versus A's 197.

Across 1,308 depth comparisons, 1,231 improve, 69 tie and eight regress by 1–18 cycles. Three rankings flip when the measurement window doubles. These outcomes remain in the [full report](stage4-results.md). Selected gains do not establish a universal advantage.

## Moving from words to useful work

The core assumes an immutable 256 KiB fixture is fully resident in both memories and excludes preload cost. It measures delivered words. The implemented application adds a real predicate-and-sum consumer, an authoritative 8 KiB B dataset, finite 1 KiB packed header storage, actual preload transactions, and a 1 KiB whole-record cache as an alternative. A CSV entry point runs user data through native RTL and exports ordered ID/selection/sum results.

The final application matrix has **384 native runs / 96 matched configurations** and **122,880 checked record results**. It compares eager hybrid fetching with a prefetched B-only path, a header-first path that skips rejected payloads, and direct-mapped whole-record caching. Forty directed outcomes and four quiescent update/invalidate/reload outcomes pass separately. Completion latency is measured from fixed release edges as well as offer and acceptance, so waiting outside a controller is visible.

The result changes the original story. At base timing, header-first nearly wins one selective scan, but its 1,876-cycle preload leaves it one cycle behind B-only. Four actual repeated scans repay that cost: 9,044 total cycles versus B-only's 14,653, a **38.3% reduction**. The eager hybrid loses that comparison. Whole-record caching instead wins a hot all-match workload, transferring 128 backing words rather than 2,048; direct-mapped conflicts erase that reuse. A subsequent update experiment changes selection and payload values, invalidates state, reloads headers and independently scores a second query epoch. These qualified findings are in the [application report](application-results.md).

## Contributions and resume wording

The user supplied the hypothesis, direction, fairness requirements and stage approvals. AI generated implementation, tests, tooling, analysis and documentation under that direction. User decisions and AI implementation are distinct contributions. This is an inspectable engineering investigation, not a claim that the user personally wrote every line or invented a new architecture.

Suggested wording for an **AI-assisted SystemVerilog architecture project**:

- Led an AI-assisted study of an ordered split-memory streaming controller, specifying ready/valid, synchronous-memory, ownership and reset contracts across one- and two-slot designs.
- Extended the study into a native RTL record filter/sum prototype with finite placement, a whole-record cache, a CSV interface and measured preload/update costs; evaluated 384 matched application runs and 122,880 record results.
- Evaluated 2,616 native RTL benchmark runs with 98.8 million independently checked output words; compared both single-memory baselines and reported throughput, tail latency, losing cases and phase sensitivity.
- Directed verification with 229 directed outcomes and 232 seeded/reset/fault outcomes, including paired checker faults and exact depth-one compatibility with historical results.

A technical walkthrough should explain an independent A/B ownership transition, why a held final word retains its slot, how the address-only checker catches wrong routing, and why a selected 27.3% simulation gain is not a general hardware claim.
