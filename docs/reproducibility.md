# Reproduce the simulations

Python generates fixtures, builds the native Verilator executable, checks its output, and produces reports. It does not simulate the DUT. The tested development environment is macOS arm64 with Verilator 5.048 and Python 3.9.6. Linux/WSL setup is documented in [setup](setup.md); distinguish documented instructions from an actually executed platform check.

## Start with the application

The finite-tier application has a self-contained runner and does not need historical benchmark archives. After installing Verilator, Make and a C++ compiler:

```sh
bash scripts/test_record_reduce.sh
bash scripts/test_record_cache.sh
bash scripts/test_application.sh
python3 tests/test_application_accounting.py
python3 tests/test_application_report.py
python3 benchmarks/report_application.py
python3 benchmarks/report_application.py --check
```

These commands compile and execute RTL, retain failure diagnostics, and write new application evidence. Inspect each runner's command-line help for any supported narrower subset. Do not call a selected/pilot run the full benchmark.

## Core checks and historical evidence

```sh
bash scripts/check_core.sh --quick
bash scripts/check_core.sh --list
```

`--quick` runs tool checks, strict core lint, a native smoke test, original accounting tests and runner-contract checks. It is not the full controller regression. The full `check_core.sh` command runs all native correctness suites and audits existing raw performance records. `--evidence` audits saved core records without compiling RTL. These latter modes require the complete raw evidence hierarchy.

The public source snapshot contains source, concise technical documentation and derived comparison tables/figures. Almost 1 GB of historical raw records, private development logs, internal instruction files, local tools and unrelated resume files are intentionally not part of that snapshot. A table or figure alone is not a substitute for a raw-record audit. The complete development archive remains local. To independently recreate raw records from a **fresh source checkout**:

```sh
bash scripts/reproduce_core.sh > core-reproduction.log 2>&1
```

This runs native correctness first, generates the 78-run original reference, seals its hashes, executes its replay and the 1,230 richer-profile runs, then the 2,616 common-core runs, Stage 5 stress/reset checks, and the complete core audit. A rebuilt P0 equivalence claim is against that newly generated local reference; it is not a comparison to a downloaded historical archive. This is a long benchmark workflow and creates roughly 1 GB of raw evidence plus temporary native builds. It refuses existing historical output directories rather than replacing them.

All memory/sink settings are recorded per run. Comparisons match workloads, readiness and memory settings across designs. Expected-failure runs must exit nonzero with their designated diagnostic; compilation failure and generic timeout do not count. Passing summaries are bound to source hashes. Keep historical reports immutable when changing the implementation.

Plots are optional and use the versions in `benchmarks/requirements-plot-lock.txt`; native simulations, fixtures and measurements use only the Python standard library. Do not infer hardware timing, synthesis or physical memory behavior from these modeled cycles.


## Executed packaging checks on 2026-11-02

The complete application campaign and CSV example were executed from the source-only publication snapshot in a separate directory. All 384 native result CSVs, metrics and four update results exactly match the development reference. The full current-checkout core regression also passes all fifteen recorded commands against frozen sources. Source-keyed compiler caches on this same macOS host may be reused; no independent Linux/compiler qualification is claimed. Full fresh core reconstruction also passed: 4,002 native benchmark runs (78 original P0, 78 replay, 1,230 profiled and 2,616 buffered), all prerequisite correctness suites and the final report audit. All 2,616 buffered per-block CSVs and metrics match the development reference exactly; the 78 original P0 and 1,230 profiled records also match. These are reproductions of existing configurations, not additional experimental cases. The [machine-readable receipt](../results/reproducibility-summary.json) records scope and source hashes.
