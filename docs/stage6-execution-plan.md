# Stage 6 core evaluation plan — 2026-11-02

The user requested progressing the project as far as possible in one run, improving quality where useful, and updating GitHub. This authorizes the remaining core evaluation and presentation work. It is not a claim that the user has reviewed the completed results. During execution, the user additionally authorized a useful application extension; its separate contract is [application-contract.md](application-contract.md). That extension does not change the preserved core evidence or this core analysis. Automatic-selection, outstanding-depth, boundary-bypass and hardware gates remain unchanged.

This plan is recorded before executing the new analysis. The historical Stage 4 matrix already covers the approved Stage 6 comparison axes: 436 configurations × three modes × two capacities = 2,616 native runs. Stage 6 will consolidate and independently re-account those records, rather than repeat identical simulations or add an outcome-selected benchmark matrix. No production RTL, model, workload or benchmark-runner change is planned. If a source mismatch or accounting failure is found, stop the report and resolve it before using any number.

## Fixed analysis and checks

- Require the exact complete Stage 4 matrix, current implementation/input hashes, passing per-run records and native logs. Recompute every recorded metric from its per-block CSV using the preserved accounting implementation; compare every depth-one shared field to the original historical records.
- Keep primary, ablation, aggregate-rate, short-window, sensitivity and other supplementary groups separate. Never pool unlike configurations into an overall performance percentage.
- Report both baseline comparisons at equal capacity for each P0–P3 primary cohort. P1–P3 headline cohorts use recommended settings, sequential access and early delivery on; each has the six predeclared geometries/splits and four traces.
- Export every matched case/depth with first-word, mean/p99 completion, steady throughput and source-record links. Analyze depth changes within each mode, early-on/off pairs, sequential/conflict workloads, split differences and fixed-trace ranges.
- Retain every depth regression and every doubled-window ranking flip. Explain command-acceptance queueing and distinguish startup timing from whole-run and steady throughput. Fixed-trace ranges are not confidence intervals.
- Add deliberate report-audit faults for stale sources, missing/duplicate configurations, unmatched settings, altered records and altered metrics. These test analysis integrity, not RTL correctness.
- Generate a concise standalone figure and deterministic JSON/CSV/Markdown results under `results/core-*`. Existing evidence under `results/raw/` and historical reports remain read-only.

## Interpretation and checkpoint

Data assembly storage is depth × N × 32 bits plus registers/metadata. Equal assembly storage does not give hybrid equal interface or source-memory cost. Both stores hold the entire immutable 256 KiB fixture; capacity, placement, preload/update costs and useful application work are not measured by this core matrix. Timings are exploratory simulation parameters, not physical device measurements. Stage 6 completes the core evaluation only; the completed core remains the reference for the separately contracted application experiment.

The final report will list only checks actually executed and distinguish a new analysis of preserved native evidence from a newly executed simulation campaign. Any fresh project-wide regression results belong in the current validation log, not in historical simulation counts.
