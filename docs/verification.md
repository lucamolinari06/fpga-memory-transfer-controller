# Verification contract, executed Stage 2 suite and future plan

The current regression passes all 36 Stage 2 cases (31 positive, five intended failures) and 32 Stage 3 cases (28 positive, four intended failures). Implemented suites are described below; double buffering, randomized testing and the full fault campaign remain future work. No coverage percentage is claimed.

## Stage 0 smoke and current evidence

`sim/tb/smoke_tb.sv` checks synchronous reset, two increments, enable-low hold, reset during operation, and restart of an eight-bit counter. It drives inputs at falling edges, compares after rising-edge updates, and has a timeout. Its comparisons and `$fatal` calls execute in SystemVerilog when the simulator is available. The clock generator uses nonblocking assignment. An actual Verilator `PROCASSINIT` warning was fixed by moving declaration-time initialization into `initial` blocks; strict warnings remain enabled.

On 2026-10-21, initial smoke/lint attempts failed because Verilator was missing. After local installation and correction of `PROCASSINIT`, strict lint and actual SystemVerilog compilation/execution passed, with `PASS smoke: reset, increment, hold, active reset` and `$finish` at 66 ns. Initial failures are retained separately; `build/smoke.log` is the latest successful run. The tool-check script now attempts every version query. Exact commands, versions and outcomes are in PROJECT_STATUS.md and docs/validation/.

The counter test does not exercise ready/valid, RAM ports, early validity, reset cancellation of transactions, or any memory controller. It does not check wraparound or establish a general correctness proof.

## Independent specification oracle

The golden transaction sequence derives only from **accepted block commands**: append N logical word addresses `base + 0 ... base + N-1` in command acceptance order. On every `out_valid && out_ready && !rst`, pop one expected address, compare data against that address's deterministic source value, and require last exactly at N-1. Reject output when the queue is empty. The checker must not use S, bank addresses, response arrival order, DUT validity counts or DUT read pointers to decide expected output order.

Implemented source function: `data(a) = (a * 0x9e3779b1 + 0xa5a55a5a) mod 2^32`. The odd multiplier makes addresses distinct within the 32-bit domain. Generate memory fixture contents with Python integer arithmetic; compute the scoreboard's expected value independently in testbench arithmetic, using fixed golden address/data vectors to validate both implementations. Do not share the controller's routing or merge functions with either oracle. A different implementation of the same simple source formula does not make two independent proofs; the central independence is expected **logical order derived from commands**.

The behavioral source serves fixture data for the address in the accepted memory request. It must not generate output based on the expected consumer sequence: wrong controller requests must produce wrong data that the checker detects. Use multiple, disjoint nonzero block bases, not only base zero or identical repeated blocks. Protocol monitors independently compare accepted request address/count and number of responses against the architecture contract; these monitors may inspect split settings, but the end-to-end scoreboard may not.

Reset clears the expected command queue and records an aborted epoch. The post-reset command sequence uses distinct addresses to expose stale responses. Monitor reset cancellation even when data happens to match. Do not count old commands as successful completions. Expected queue empty is insufficient to finish: require no outstanding request/held output and a bounded quiet tail to detect extra delayed outputs.

## Assertions and directed checks before randomized tests

| Area | Required checks |
| --- | --- |
| Handshakes | Counts change only on acceptance; valid/data/address/count/last stable under stalls, unless reset cancels them; no dependence on ready to first assert valid |
| Request ownership | At most one outstanding request per interface, no zero-length request, no response without ownership, no second acceptance on final-response edge |
| Response correctness | Exact beat count and last marker, address bounds, no writes to a free slot, no duplicate write to a committed word |
| Validity and reads | Pre-edge committed counts authorize reads; no same-edge write/read to the same address; no reads of invalid/uninitialized data |
| Output pipeline | Read issues and consumed words counted separately; output stable while stalled; bank-select and last advance with the correct word; one output slot reserved |
| Lifecycle | No slot freed until all expected writes and consumptions complete; no overwrite of unread or output-held data; FIFO block order |
| Reset | No transfers counted while reset high; active models discard requests; partial slots/output invalidated; new requests alone populate new output |
| Parameters | N=1,2,8,256; S=0,1,N-1,N where valid; reject N=0, non-powers-of-two, N>256, split outside bounds, unsupported width/multiword beats |

Stage 2 first establishes A-only and B-only with a single slot, always-ready and periodic/backpressured sinks, variable latency/rate/burst gaps, nonzero bases, multiple blocks and reset. Stage 3 adds S interior/endpoints, both arrival orders, independent request acceptance delays, simultaneous responses, B-first suffix retention, and the exact eight-word trace expectations. Stage 4 adds two-slot overlap, both slots occupied, early completion of one interface's next segment, long stalls on the last word, and reset with both slots occupied. Each stage must pass its directed tests before proceeding.

Exercise reset when idle, holding an unaccepted request, awaiting first response, after partial prefix/suffix writes, with B complete before A, with an output held under backpressure, on a potential final-beat edge, and with a slot ready for handoff. Drive reset away from rising edges to avoid testbench races. Controller-only reset is an explicit unsupported scenario; a test must not present it as a supported recovery guarantee.

Random tests use recorded seeds, configuration, fixture checksum, simulator/build version, and the same independent oracle. Vary bounded request stalls, response release delays, sink patterns and reset points. An outstanding valid response cannot be withdrawn by a random delay. Record both a no-progress timeout and a total-run bound sized for configured maximum latency/gaps/stalls; do not label a deliberately permanently stalled sink a controller deadlock. Save failing seeds, logs and waveform traces for reproduction.

## Checker effectiveness (later, required before benchmarks)

Inject faults only in a test wrapper or temporary build, never production RTL:

- Flip one data bit: expect an address-specific data mismatch.
- Duplicate or reorder a word: expect sequence/data/last or unexpected-output failure.
- Drop a word: expect the next data mismatch, early-last/length failure, or bounded timeout if the final word disappears.
- Early/late last marker and an unsolicited response: expect protocol monitor failures.
- Attempt a premature free/invalid read in a dedicated negative variant: expect ownership/validity assertion failure.

The runner must match the intended failure category and require a nonzero exit; a compile failure or unrelated timeout does not count as detecting corruption. Run the unmodified build to a pass with the same seed. Preserve representative failure logs. Do not derive benchmark results from faulted builds.

## Scope limits

Verilator execution is a simulation check, not proof over all inputs, analog timing, or metastability analysis. Treat validity explicitly rather than relying on X propagation to expose uninitialized storage in a two-state simulation. No coverage percentage is claimed without an actual coverage build and reviewed report. Synthesis, RAM inference, device timing, and physical operation remain separate later evidence.

## Implemented Stage 2 suite

`bash scripts/test.sh` runs Python orchestration that generates a 65,536-word fixture, builds native Verilator binaries, and executes SystemVerilog checks. Python is not simulating the controller. All builds use `--timing --assert -Wall`; baseline builds also enable optional VCD tracing. Expected-output construction lives in `address_scoreboard.sv`, which has no split parameter or DUT/internal-bank inputs. Memory models read the fixture by requested address. Golden vectors cross-check fixture generation and the SV arithmetic oracle.

The directed matrix includes A-only/B-only default and minimum timing; burst gaps with sink stalls; request stalls; a witnessed stall on the final word; reset while a request is stalled, before the first response, after partial arrival, and while output is held; and multiple consecutively offered commands. Boundary builds cover N=1,2,8,256 and S=0,1,N-1,N where listed in the runner. Baseline checks include exact configured response timing, a two-edge minimum write-to-consume delay, exact first-word latency and absence of unnecessary within-block bubbles for an always-ready sink, and an early-consumption witness. Reset uses a new address region and clears the checker epoch.

A separate `memory_tb.sv` uses absolute edge deadlines to check the countdown-based memory model, including response backpressure, two overlapping offered requests, burst gaps and request cooldown. This covers memory response stalls that do not normally arise from the baseline's preallocated full-block storage.

Five negative cases deliberately corrupt data, misalign a command, or select N=3, N=257 or S=9 with N=8. Each must fail with its named diagnostic; build failures and unrelated timeouts do not count. The corruption is applied only in the testbench output wrapper, not production RTL. This establishes one corruption-check witness, not completion of the Stage 5 corruption/drop/duplicate campaign. No randomized tests are run in Stage 2; recorded seed is null.

Imperative testbench scoreboards/protocol monitors locally waive BLKSEQ because they update simulation reference state with blocking assignments in one process. Synthesizable RTL has no warning waivers. Production state uses nonblocking assignments. The pipeline stability properties, count/ownership invariants, read/write bounds, collision checks and last-marker checks execute with assertions enabled.

Each simulation has a 200,000-cycle baseline timeout (10 ns test clock), and the runner adds a wall-time limit. After expected completion, a quiet tail checks for extra output and outstanding work. On an unexpected simulation failure the runner repeats with VCD tracing and retains build products; logs and event CSVs remain under build/stage2. The JSON summary records configurations, expected failure classes, exit codes, fixture/source hashes and simulator version. Preserved checkpoint evidence lives under docs/validation/stage2. These checks cover the listed directed scenarios, not all legal inputs or timing patterns.


## Stage 3 directed verification

The hybrid suite uses the same `address_scoreboard.sv`, unchanged: expected words still come solely from accepted command addresses. A separate public-channel protocol monitor checks per-interface request address/count, ownership, latency/beat spacing and empty-segment inactivity. It asserts that each pending nonempty request becomes valid independently of the other interface's ready/acceptance state. It records actual arrival addresses/edges and checks synchronous latency and ordered delivery; this timing monitor does not define the end-to-end data sequence.

`tests/run_hybrid.py` compares two simulated eight-word transactions against fixed edge lists transcribed from the approved architecture tables, normalized to their common request edge. It checks every arrival and consumption edge and the held w3 at edges 11/12 in the A-first example. These expectations are not generated by a split/merge reference controller. Handshake CSVs preserve the actual evidence.

Other directed cases require witnesses for simultaneous response writes, A consumption before B request acceptance, B completion before A request acceptance, periodic consumer backpressure, burst gaps/cooldowns, all data arriving during a sink stall, and final-word hold. Reset cases explicitly reach A-only request acceptance, B-only request acceptance, suffix complete with no prefix data, partial prefix arrival, held output, and held final output before shared cancellation. Post-reset work uses a distinct address region; prior expected work is discarded as an aborted epoch. Multiple blocks are tested with the slot reused only after consumption.

Boundary configurations cover N=1,2,8,256 with S=0,N and interior splits. Four expected-negative cases check corruption (DATA_MISMATCH), an incorrect A last marker (A_RESPONSE_LAST), N=3 (PARAM_BLOCK_WORDS), and S=9 with N=8 (PARAM_SPLIT_WORDS). Faults live in the testbench wrapper. Passing negative tests require the named assertion category and nonzero status; compilation failures and unrelated timeouts cannot count as checker success.

`bash scripts/test.sh` now runs both stage suites. `bash scripts/test.sh stage2` and `bash scripts/test.sh stage3` select one; `bash scripts/test_hybrid.sh --case example_b_first` rebuilds/runs a named hybrid case. A selected run writes selected-summary.json and does not masquerade as the full suite. Full reports, logs and event CSVs are under build/stage3, with source and fixture hashes and optional failure VCDs. Stage 3 remains directed, with seed=null; it does not claim the later randomized/fault campaign, benchmark fairness measurements, or physical synthesis validation.

## Single-buffer benchmark interlude before Stage 4

The user requested this bounded performance checkpoint before double buffering. The common `benchmark_tb.sv` elaborates one A-only, B-only or hybrid controller; all use the existing independent address scoreboard and shared behavioral models. No DUT internal state feeds measurement counters. The testbench separately checks mapping, outstanding ownership, exact response timing, synchronous consumption delay, full-block-gate behavior when selected, counts and quiet drain. Reset is shared at startup and never interrupts a benchmark window.

Both controllers now expose `EARLY_DELIVERY`, default 1. Setting it to 0 adds only a committed-full-block condition to read issue. The 36 baseline/model and 32 hybrid correctness cases were rerun with the default. The gated variant is exercised by data-checked default and slow-sink benchmark workloads; it does not claim a separate exhaustive reset/parameter campaign.

`benchmarks/run_single_buffer.py` requires passing full stage reports with matching source hashes. It checks per-block CSV invariants, fixed hand-derived edge expectations for default/equal-fast/gated runs, independently computed ready-clock counts, exact busy/request timing, window boundaries, and endpoint equivalence. Every benchmark has an address-by-address end-to-end check and a quiet drain; a checksum alone cannot establish correctness. `benchmarks/test_measurements.py` uses a retained two-block RTL trace to check the expected 33-interval whole / 17-cycle steady window, then deliberately removes/duplicates blocks or corrupts stalls, occupancy, busy counts or request timestamps. All eight measurement tests pass.

The primary sweep is directed, not randomized. It is deliberately narrower than Stage 5: no new broad drop/duplicate/fault-injection campaign or two-slot handoff coverage is claimed. See `docs/single-buffer-benchmark-contract.md` for all measurement and fairness conventions, `docs/results.md` for interpretation, and `results/raw/single_buffer/` for the complete executed configurations and raw evidence.

## Implemented timing-model verification

The user approved the timing extension before implementation. The original 68 correctness outcomes, smoke, original measurement tests and P0 results were replayed without changing the controller, bank, address oracle or historical model/harness. The new seven-top strict lint includes both new testbenches.

`tests/run_memory_timing.py` executes 28 model outcomes: 16 positive cases and 12 expected negatives. Fixed expectations cover cold/hit/conflict row latency, bank/row/chunk crossings and unaligned B addresses; exact shared grants/responses; L=1 same-edge initial grant and consecutive grants; held/final responses across reservation/maintenance; setup cancellation; witnessed resets during setup, waiting service, pause, one accepted descriptor, one/two response registers full; and four prerecorded schedules. Reset resumes with fresh addresses. Calendar output is independently compared against saved event schedules, including idle/stalled edges. Missing, malformed, trailing-garbage and exhausted files fail with named diagnostics. Eight wrapper faults test withdrawal, held-payload mutation, duplicate data, incorrect last, shared overcapacity, a locally reserved grant, a stale response after cancellation reset, and a dropped response. Expected failures require the intended diagnostic and nonzero status; unrelated timeouts/compile failures do not pass. Model waveforms and event CSVs are retained, including expected-negative examples.

`run_memory_timing.py --verify-only` runs 31 controller integrations: the hand-derived example, 24 mode×early-state×trace cases, and six witnessed held-output shared resets. The example's consumer edges 4/7/8/9 follow grants 1/3/4/5 and writes 2/4/5/6, with B's row primed through a public request. The independent address_scoreboard remains unchanged. The new service_monitor independently checks public-channel data/order/last, descriptor ownership, response stability, grant/holding conservation, service capacity, calendar exclusions and latency/spacing lower bounds. Fixed expectations provide an additional timing oracle rather than copying the scheduler into the data checker.

Eight new accounting tests use actual RTL CSV records: one fixed 29-interval whole / 11-cycle steady example, and seven mutations covering service counts, sink-ready partition, busy occupancy, first-valid timestamp, address, slot occupancy and shared capacity. Every performance run separately checks the independent output stream, public-channel invariants, synchronous response-to-consumption delay, early-off behavior, exact accounting, quiet drain and timeouts. Endpoint metrics match their baseline under each new overlay.

The predeclared matrix executes 78 exact P0 replays plus 1,230 new-profile runs. Inputs are generated before performance execution, with per-run source/input hashes, finite calendar bounds, constant workload seed and paired disturbance seeds. All 846 non-short P2/P3 steady windows include maintenance-start events. Doubled windows expose a fragile seed-29 ranking, which is reported explicitly. Validation evidence is under docs/validation/memory-timing; raw runs are under results/raw/memory_timing. No exhaustive coverage, Stage 5 completion, synthesis or hardware operation is claimed.

## Proposed Stage 4 verification and measurement changes

[stage4-contract.md](stage4-contract.md) defines the next, not-yet-executed suite. Gate two-slot comparisons on depth-one equivalence to the unchanged historical controllers. Add witnessed overlap, differing A/B destination slots, pinned requests during FIFO head changes, simultaneous enqueue/retire, full-queue backpressure, wraparound, final-output hold and shared cancellation with both slots occupied. Reuse the independent address queue; augment a separate public-channel ledger, not its data oracle.

The new measurement harness must allow up to two accepted commands and associate each response with its accepted request owner. Across warmup boundaries, assert response-minus-consumption equals backlog change; for P1–P3, grant-minus-response equals held-model-word change. Occupancy is accepted commands minus completed blocks, not the historical single-slot formula. P0 transport-grant metrics remain not applicable. Compare all three modes at the same depth, then isolate depth-one/depth-two differences within each mode. These are planned changes; no new RTL test was run for this documentation checkpoint.


## Stage 4 verification in progress

The new buffered harness uses the unchanged address-only scoreboard. A separate two-entry public-command record ring assigns each interface’s requests to command ordinals, tracks response arrival edges, and asserts consumption at least two edges after arrival. At depth one, the original controller runs alongside the new core on identical public stimuli; ready/valid and valid payloads are compared every edge. The public ring is independent of DUT slot indices. Internal DUT signals are used only for structural assertions and coverage witnesses, never expected data.

`test_buffered.sh` is the new directed verification entry point; `benchmark_buffered.sh` preserves the full 436-configuration, six-run-per-configuration matrix. Two-slot accounting uses post-edge command occupancy and response-minus-consumption backlog. Historical row/grant columns retain their pre-edge model-counter convention for exact depth-one comparisons; the new `grant_count` column counts public grant events including the edge and is used for holding conservation and shared-capacity assertions.


Stage 4 completion, 2026-10-22: 205 positive matrix cases, 21 additional structural/reset/fault outcomes, three parameter rejections and ten accounting tests pass. All 2,616 performance runs also use address-based checking and protocol assertions. See [Stage 4 results](stage4-results.md) and `docs/validation/stage4/` for actual commands, logs and evidence. This finite campaign is not Stage 5 or exhaustive verification.

## Stage 5 recorded-seed stress and fault verification

The user approved Stage 5 on 2026-10-22. The frozen execution plan (development archive) defines four seed schedules, two geometries, P0/P3, three modes, two slot counts and both early settings. A separate `stage5_stress_tb` composes finite exogenous request-admission/response-release gates, command offers and sink readiness with the original behavioral/profiled memories and unchanged `address_scoreboard`. The schedule is generated before any run from seed and absolute reset-relative cycle; no DUT valid, response or output signal drives it. Each sixteenth edge opens all gates, so deliberately imposed off-runs are bounded. The memory-side response register remains held while its external release gate closes. The controller sees a response only on a release edge, and the existing service monitor observes the raw memory side.

The Stage 5 command driver retains valid and base under a stall. Its own sampled assertion checks that property; public controller request stability, response ownership, synchronous consumption and quiet drain remain active in the borrowed benchmark monitor. Shared reset clears the controller, both memory models, replay epoch, sink, driver and scoreboard; a disjoint in-range post-reset address region exposes stale work. The main reset matrix samples edge 12. A recorded addendum samples edges 5 and 25 and retains actual occupancy/owner witness strings. These samples do not imply exhaustive reset-state coverage; Stage 4 directed checks remain the held-output/pending-request mutation reference.

Faults affect only the scoreboard input wrapper: one-word bit flip, duplicate or adjacent swap, middle drop, final drop, early/late last and extra output. Every one uses a same-seed clean native control and a named nonzero diagnostic. The `tests/audit_stage5.py` checker rereads saved schedules, hashes all inputs/sources, validates matrix/fault pairing and checks Stage 4 source preservation. Native logs, exact finite inputs, records and build logs are archived under `results/raw/stage5/`; selected failure logs and compressed VCDs live in `docs/validation/stage5/`. The campaign provides finite seeded evidence, not random coverage percentages, formal proof or hardware validation. No faulted run is used for performance claims.


## 2026-11-02 core consolidation and useful application

The [Stage 6 report](stage6-results.md) independently re-accounts 2,616 preserved native benchmark runs and all 1,308 historical depth-one shared-field matches. Sixteen deliberate report-integrity tests pass. The original RTL/model/scoreboard sources remain unchanged. Fresh native regressions and public-source reconstruction are recorded separately from the historical benchmark counts.

The [finite-tier application](application-results.md) adds independent fixture/address-based checking of ID, selection and 64-bit sum for every record. Its final native campaign passes 40 correctness outcomes (20 positive, 20 named failures), four quiescent update/invalidate/reload outcomes, and 384 matched benchmark runs with 122,880 checked record results. Seven application-accounting tests and fourteen report-provenance tests pass. The report binds declared timing controls, exact seeded fixture/workload contents, intended fault diagnostics, native arguments, source hashes and raw records; a self-consistent but wrong configuration fails.

Standalone reducer checks pass three native outcomes (one multi-scenario positive and two named failures). Cache checks pass ten native outcomes covering hits, collisions, refill, stalled descriptors/results, four reset phases, request/response errors and checker corruption. These are finite directed tests, not formal proof or a coverage percentage. The public CSV example also passes all four architectures with identical 128 outputs and 32 selected records at threshold 25.

Actual query execution and header preload are separately measured. A fixed release edge `2*i` exposes waiting before acceptance, and ready schedules depend only on workload clock. Quiescent updates retain both epoch ledgers and account for actual two-write handshakes, a quiet guard, shared reset and repeated preload. The initial preload-address scheduling race was a testbench defect, corrected before the entire source-matched campaign was rerun; its log remains in the development archive.
