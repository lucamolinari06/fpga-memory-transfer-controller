# Stage 5 verification checkpoint — 2026-10-22

## Result and scope

All **232 final native outcomes pass**: 192 distinct clean cross-product runs, 24 shared-reset runs and eight fault pairs (eight clean repeat controls plus eight named expected failures). Strict `--assert -Wall` lint and the full existing Stage 4 correctness suite pass. No production RTL, memory model, address scoreboard, sink model or historical benchmark source changed. The Stage 4 benchmark source hashes still match the saved 2,616-run report; the performance benchmarks were not rerun because their implementation and inputs did not change. Stage 5 makes no new throughput or hardware claim.

The clean matrix is four recorded seeds × two geometries × P0/P3 × three modes × one/two slots × early delivery off/on. It checks N=8,S=3 and N=32,S=8, eight accepted blocks each. Seeds 101/202/303/404 respectively select sequential/permuted/conflict/expanded aligned base orders. Each seed's finite command-offer, sink-ready, A/B request-admission and A/B response-release schedule is reused across the three modes and both capacities. The same P3 calendar is reused as well. Different request histories naturally change which predeclared service opportunities are taken; P3's existing arbiter grants eligible paths under its shared reservations. This is correctness stress, not a fair performance ranking; workload type is coupled to seed in this matrix.

The schedule is generated from a recorded seed and absolute reset-relative cycle before simulation, never from DUT valid/output. Every sixteenth edge opens all six gates. Across the four 200,000-edge files, actual longest closed runs are at most ten edges per gate. The raw memory response holds valid/data/last across a closed release gate; the service monitor sees that raw side, while the controller sees a beat only when released. Controller request descriptors and output still obey stable ready/valid. The unchanged command-address scoreboard checks every accepted output word independently of split, bank indices, response order and DUT validity counters. Public ledgers retain ownership and response-to-synchronous-consumption checks. Both depths and both early settings pass.

The main 12 resets interrupt two-slot P0/P3 work at edge 12. An addendum (development archive) adds six cases at edge 5 and six at edge 25. All 24 observed a pre-reset occupied slot and passed eight post-reset blocks from disjoint in-range addresses, followed by a quiet tail. Sixteen observed an active A owner and sixteen an active B owner; none sampled a pending descriptor, held output or maintenance edge. The earlier Stage 4 directed cases still provide those distinct reset witnesses. Three phase points do not establish exhaustive reset coverage.

| Test-only scoreboard fault | Expected and observed diagnostic |
| --- | --- |
| One data bit flipped | `DATA_MISMATCH` with address and values |
| Previous word duplicated | `DATA_MISMATCH` |
| Adjacent words swapped | `DATA_MISMATCH` on first displaced word |
| Middle word dropped | `DATA_MISMATCH` on following word |
| Final word dropped | `CHECKER_MISSING_FINAL` after bounded quiet drain and exactly one pending address |
| Early last / late last | `OUTPUT_LAST_MISMATCH` in each case |
| Extra output after drain | `UNEXPECTED_OUTPUT` |

Each faulted native run exits nonzero with its intended diagnostic, and its unchanged same-seed control passes with identical input hashes. A compile failure, unrelated timeout or missing injection would fail the runner. Faults are isolated to the scoreboard-input wrapper, and faulted runs do not produce benchmark numbers. Existing Stage 4 source-mutation cases for invalid read, premature free, request/output instability and stale reset were rerun; all 21 extra outcomes pass.

## Evidence and reruns

| Executed check | Result |
| --- | --- |
| `bash scripts/test_stage5.sh` | 220 main native outcomes PASS; summary (development archive) |
| `bash scripts/test_stage5_reset_phases.sh` | 12 supplemental native reset outcomes PASS; records (development archive) |
| `python3 tests/audit_stage5.py` | 192 distinct clean configurations, 24 resets, eight clean/fault pairs, all input/source hashes and Stage 4 source preservation PASS; audit (development archive) |
| `bash scripts/test_buffered.sh` | 205 positive RTL cases, 21 extra outcomes, three parameter rejections and ten accounting tests PASS |
| `bash scripts/lint.sh`, Bash syntax and explicit-output Python compilation | PASS, strict Verilator warnings; toolchain Verilator 5.048 |
| Representative `+trace` fault replays | Data flip, final drop and unexpected output reproduce expected diagnostics with retained compressed VCDs and manifest (development archive) |

The raw archive (development archive) contains the exact finite inputs, per-run native logs and records, build logs, source/input hashes and a 755-file copy manifest (development archive). `build/stage5/` remains the executable working copy. The original Stage 4 results under `results/raw/double_buffer/` and historical P0–P3 references remain unchanged. The fixture checksum and simulator provenance are in the raw summary.

Two test-only issues were resolved before the final source-matched run. A conditional `$fatal` rendered the final-drop diagnostic numerically under Verilator; separate literal messages fixed it. The command driver initially carried a completed valid offer into the next command, reducing intended offer gaps; it now distinguishes accepted from stalled offers and asserts command stability. The final reorder wrapper explicitly defines both sides of the adjacent swap. After each wrapper change, the full Stage 5 matrix was rebuilt and rerun. An attempted supplemental reset using seed 404's full-range expanded bases plus the +32768 post-reset shift correctly tripped `MEMORY_REQUEST_BOUNDS`; the edge-25 supplement was changed to seed 101's bounded sequential bases and rerun. The two initial failing logs are retained under validation (development archive). None of these involved a production RTL/model change.

These are finite seeded simulations, not formal proof or a coverage percentage. P1/P2 are covered by the preserved directed Stage 4/timing suites but are not in this Stage 5 randomized matrix. The four seed/workload pairs do not support statistical performance inference. No physical hardware, synthesis, BRAM inference, area, clock frequency or novelty claim follows.

## Walkthrough and review

The testbench offers aligned blocks according to a saved clock schedule. Each controller mode issues its normal public requests. An exogenous gate controls when the memory may accept each request and when a held response may reach the controller. The independent scoreboard queues addresses from accepted commands and expects exactly N ordered values per block. It does not inspect the split or controller state. Shared reset clears that entire epoch; post-reset commands use a separate legal address region. Fault wrappers perturb only the checker-facing stream to prove that the named checker catches displaced, missing and extra words.

Three understanding questions:

1. Why does closing the release gate leave a memory-held response stable instead of withdrawing it?
2. Why does a middle-word drop cause an address-specific mismatch, while a missing final word needs a bounded pending-queue check?
3. Why do passing seeded reset phases complement, rather than replace, the earlier directed pending-request and held-output reset tests?