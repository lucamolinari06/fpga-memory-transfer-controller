#!/usr/bin/env python3
"""Audit preserved native RTL records and consolidate the completed core study.

No DUT simulation runs here. --check reads evidence and checks committed report
products without rewriting them. All evidence paths are repository-relative;
stored historical command lines are provenance, never executed.
"""
import argparse
import collections
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import statistics
import sys
import tempfile

import run_double_buffer as benchmark

ROOT = benchmark.ROOT
MODES = benchmark.old.MODES
SUMMARY = 'results/raw/double_buffer/summary.json'
ANALYSIS_SOURCES = ['benchmarks/report_core.py', 'benchmarks/test_core_report.py',
                    'docs/stage6-execution-plan.md']


class AuditError(ValueError):
    """An evidence or report invariant was violated."""


def require(condition, message):
    if not condition:
        raise AuditError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def json_text(value):
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n'


def safe_path(root, relative):
    path = root / relative
    require(not Path(relative).is_absolute() and root.resolve() in path.resolve().parents,
            'Evidence path must stay inside the repository: ' + relative)
    return path


def verify_hashes(root, recorded, expected_paths=None):
    require(isinstance(recorded, dict) and recorded, 'Empty source/input manifest')
    if expected_paths is not None:
        require(set(recorded) == set(expected_paths), 'Source/input manifest membership differs')
    for name, expected in recorded.items():
        require(digest(safe_path(root, name)) == expected, 'SHA-256 mismatch: ' + name)


def validate_matrix(report, cases):
    require(report.get('passed') is True and report.get('scope') == 'full',
            'Benchmark report must be passing and full')
    expected_digest = hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest()
    require(report.get('matrix_sha256') == expected_digest, 'Predeclared matrix hash differs')
    expected = {(c['name'], depth, mode): c for c in cases
                for depth in (1, 2) for mode in MODES}
    require(len(report['runs']) == len(expected), 'Missing or extra benchmark runs')
    lookup = {}
    for run in report['runs']:
        key = (run['case']['name'], run['depth'], run['mode'])
        require(key in expected and key not in lookup, 'Unexpected or duplicate run: ' + str(key))
        require(run['case'] == expected[key], 'Run case differs from predeclared matrix: ' + str(key))
        require(run.get('passed') is True, 'Failed run: ' + str(key))
        require(run.get('source_sha256') == report['source_sha256'], 'Run source manifest differs')
        cfg = dict(run['case']['args'])
        if run['case']['group'] == 'rate_control' and run['mode'] == 'hybrid':
            cfg.update(a_interval=2, b_interval=2)
        require(run['config'] == cfg, 'Unmatched memory/sink configuration: ' + str(key))
        lookup[key] = run
    for case in cases:
        inputs = [lookup[case['name'], depth, mode]['input_sha256']
                  for depth in (1, 2) for mode in MODES]
        require(all(item == inputs[0] for item in inputs), 'Unmatched input schedules: ' + case['name'])
    return lookup


def verify_run(root, run, verify_record_hash=True):
    """Re-account one raw CSV; a cached passing metric is never trusted."""
    path = safe_path(root, run['records'])
    if verify_record_hash:
        require(digest(path) == run['records_sha256'], 'Raw record hash differs: ' + run['records'])
    require('PASS benchmark' in path.with_name('run.log').read_text(),
            'Native PASS marker missing: ' + run['records'])
    stored = json.loads(path.with_name('result.json').read_text())
    require(stored == run, 'Per-run result differs from summary: ' + run['records'])
    try:
        calculated = benchmark.summarize(path, run['case'], MODES.index(run['mode']),
                                         run['depth'], run['config'])
    except (AssertionError, KeyError, ValueError) as error:
        raise AuditError('Raw accounting failed: ' + run['records']) from error
    require(calculated == run['metrics'], 'Recomputed metrics differ: ' + run['records'])


def audit(root=ROOT, progress=True):
    require(__debug__, 'Run without Python -O: preserved accounting uses assertions')
    report = json.loads((root / SUMMARY).read_text())
    sources = benchmark.SOURCES + ['benchmarks/run_double_buffer.py', 'benchmarks/run_single_buffer.py',
                                  'benchmarks/run_memory_timing.py', 'benchmarks/timing_inputs.py',
                                  'tests/run_baseline.py']
    verify_hashes(root, report['source_sha256'], sources)
    cases = benchmark.matrix()
    require(len(cases) == 436, 'Approved matrix is no longer 436 configurations')
    lookup = validate_matrix(report, cases)
    with tempfile.TemporaryDirectory(prefix='fpga-core-fixture-') as temp:
        fixture = Path(temp) / 'dataset.hex'
        benchmark.old.dataset(fixture)
        require(digest(fixture) == report['fixture_sha256'], 'Fixture hash differs')

    historical = {}
    evidence_hashes = {SUMMARY: digest(root / SUMMARY)}
    for name in ['results/raw/single_buffer/summary.json', 'results/raw/memory_timing/summary.json']:
        history = json.loads((root / name).read_text())
        require(history['passed'] and history['scope'] == 'full', 'Historical report is not full/passing')
        verify_hashes(root, history['source_sha256'])
        require(history['fixture_sha256'] == report['fixture_sha256'], 'Historical fixture differs')
        evidence_hashes[name] = digest(root / name)
        for run in history['runs']:
            key = (run['case']['name'], run['mode'])
            require(key not in historical, 'Duplicate historical reference')
            historical[key] = run

    checked_inputs = {}
    reference_matches = 0
    for index, run in enumerate(report['runs'], 1):
        case = run['case']
        expected_paths = {f'results/raw/double_buffer/inputs/{case["workload"]}_n{case["N"]}.hex', 'dataset'}
        if case['profile']:
            expected_paths.add(f'results/raw/memory_timing/inputs/seed{case["seed"]}_length{benchmark.bound(case, case["seed"])}.txt')
        require(set(run['input_sha256']) == expected_paths, 'Input manifest membership differs')
        require(run['input_sha256']['dataset'] == report['fixture_sha256'], 'Run fixture differs')
        for name, expected in run['input_sha256'].items():
            if name == 'dataset':
                continue
            if name not in checked_inputs:
                checked_inputs[name] = digest(safe_path(root, name))
            require(checked_inputs[name] == expected, 'Input hash differs: ' + name)
        verify_run(root, run)
        if run['depth'] == 1:
            ref = historical[case['name'], run['mode']]
            ref_rows = benchmark.rows(safe_path(root, ref['records']))
            actual_rows = benchmark.rows(safe_path(root, run['records']))
            require(len(ref_rows) == len(actual_rows), 'Historical row count differs')
            require(all(all(row.get(key) == value for key, value in refrow.items())
                        for row, refrow in zip(actual_rows, ref_rows)),
                    'Depth-one historical field mismatch: ' + case['name'])
            reference_matches += 1
        if progress and index % 300 == 0:
            print(f'Audited {index}/2616 native records', flush=True)
    for case in cases:
        if case['S'] in (0, case['N']):
            mode = 'B-only' if case['S'] == 0 else 'A-only'
            for depth in (1, 2):
                require(lookup[case['name'], depth, mode]['metrics'] ==
                        lookup[case['name'], depth, 'hybrid']['metrics'], 'Endpoint identity differs')
    return report, lookup, dict(native_runs=len(report['runs']), matched_sets=len(cases),
        recomputed_metric_sets=len(report['runs']), depth_one_historical_matches=reference_matches,
        native_output_words=sum((r['case']['warmup'] + r['case']['measured']) * r['case']['N'] for r in report['runs']),
        unique_inputs=len(checked_inputs), source_sha256=report['source_sha256'],
        input_sha256=checked_inputs, evidence_sha256=evidence_hashes,
        analysis_sha256={name: digest(root / name) for name in ANALYSIS_SOURCES})


def outcome(candidate, reference):
    return 'win' if candidate < reference else 'loss' if candidate > reference else 'tie'


def counts(values):
    counter = collections.Counter(values)
    return {key: counter[key] for key in ('win', 'tie', 'loss')}


def analyze(report, lookup, provenance):
    comparisons, depths, controls, flips = [], [], [], []
    cases = benchmark.matrix()
    for case in cases:
        name = case['name']
        for depth in (1, 2):
            runs = {mode: lookup[name, depth, mode] for mode in MODES}
            row = {key: case[key] for key in ('name', 'family', 'group', 'profile', 'seed', 'N', 'S', 'early', 'workload')}
            row['depth'] = depth
            for label, mode in zip('ABH', MODES):
                run, metrics = runs[mode], runs[mode]['metrics']
                row[label + '_rate'] = metrics['steady']['words_per_cycle']
                row[label + '_cycles'] = metrics['steady']['cycles']
                row[label + '_whole_rate'] = metrics['whole']['words_per_cycle']
                row[label + '_whole_intervals'] = metrics['whole_intervals']
                row[label + '_startup_first'] = metrics['startup_first']
                for metric in ('command_first', 'command_complete', 'request_first', 'request_complete'):
                    for stat, value in metrics['latency'][metric].items():
                        row[label + '_' + metric + '_' + stat] = value
                row[label + '_records'] = run['records']
            for label in 'AB':
                row['H_vs_' + label] = outcome(row['H_cycles'], row[label + '_cycles'])
                row['whole_H_vs_' + label] = outcome(row['H_whole_intervals'], row[label + '_whole_intervals'])
                row['H_p99_vs_' + label] = outcome(row['H_command_complete_p99'], row[label + '_command_complete_p99'])
            row['H_over_best_rate'] = row['H_rate'] / max(row['A_rate'], row['B_rate'])
            comparisons.append(row)
        for mode in MODES:
            one, two = [lookup[name, depth, mode]['metrics'] for depth in (1, 2)]
            depths.append(dict(case=name, profile=case['profile'], group=case['group'], mode=mode,
                one_cycles=one['steady']['cycles'], two_cycles=two['steady']['cycles'],
                delta_cycles=two['steady']['cycles'] - one['steady']['cycles'],
                outcome=outcome(two['steady']['cycles'], one['steady']['cycles'])))
        if case['early'] == 0:
            on_name = name.replace('_early0', '_early1') if case['family'] == 'path' else name.removesuffix('_gated')
            for depth in (1, 2):
                for mode in MODES:
                    on, off = lookup[on_name, depth, mode], lookup[name, depth, mode]
                    require(on['config'] == off['config'] and on['input_sha256'] == off['input_sha256'],
                            'Early-delivery pair differs beyond early setting')
                    a, b = on['metrics'], off['metrics']
                    controls.append(dict(case=on_name, profile=case['profile'], depth=depth, mode=mode,
                        outcome=outcome(a['steady']['cycles'], b['steady']['cycles']),
                        early_cycles=a['steady']['cycles'], gated_cycles=b['steady']['cycles'],
                        early_startup_first=a['startup_first'], gated_startup_first=b['startup_first'],
                        early_command_first_mean=a['latency']['command_first']['mean'],
                        gated_command_first_mean=b['latency']['command_first']['mean']))

    paired = {(row['name'], row['depth']): row for row in comparisons}
    for case in cases:
        if case['family'] == 'path' and case['group'] == 'sensitivity':
            for depth in (1, 2):
                short, long = paired[case['name'].removesuffix('_long'), depth], paired[case['name'], depth]
                for label in 'AB':
                    if short['H_vs_' + label] != long['H_vs_' + label]:
                        flips.append(dict(case=case['name'], depth=depth, baseline=label,
                            short=short['H_vs_' + label], long=long['H_vs_' + label],
                            short_H_cycles=short['H_cycles'], short_baseline_cycles=short[label + '_cycles'],
                            long_H_cycles=long['H_cycles'], long_baseline_cycles=long[label + '_cycles']))

    cohorts = []
    for profile in range(4):
        for depth in (1, 2):
            chosen = [row for row in comparisons if row['profile'] == profile and row['depth'] == depth
                      and row['group'] == 'primary' and (profile == 0 or
                      (row['family'] == 'path' and row['early'] == 1 and row['workload'] == 'sequential'))]
            require(len(chosen) == (20 if profile == 0 else 24), 'Headline cohort membership differs')
            cohorts.append(dict(profile=profile, depth=depth, cases=len(chosen),
                H_vs_A=counts(row['H_vs_A'] for row in chosen), H_vs_B=counts(row['H_vs_B'] for row in chosen),
                beats_both=sum(row['H_vs_A'] == row['H_vs_B'] == 'win' for row in chosen)))

    grouped = collections.defaultdict(list)
    for row in comparisons:
        if row['family'] == 'path':
            key = tuple(row[k] for k in ('profile', 'N', 'S', 'early', 'workload', 'group', 'depth'))
            grouped[key].append(row)
    ranges = []
    for key, rows in sorted(grouped.items()):
        expected_traces = 1 if key[5] == 'slow' else 4
        require(len(rows) == expected_traces and len({r['seed'] for r in rows}) == expected_traces,
                'Incomplete declared trace group')
        row = dict(zip(('profile', 'N', 'S', 'early', 'workload', 'group', 'depth'), key))
        row['traces'] = expected_traces
        for label in 'ABH':
            for field in ('rate', 'command_first_mean', 'command_complete_mean', 'command_complete_p99'):
                values = [r[label + '_' + field] for r in rows]
                row[label + '_' + field + '_min'] = min(values)
                row[label + '_' + field + '_max'] = max(values)
        row['H_over_best_rate_min'] = min(r['H_over_best_rate'] for r in rows)
        row['H_over_best_rate_max'] = max(r['H_over_best_rate'] for r in rows)
        ranges.append(row)
    regressions = [row for row in depths if row['outcome'] == 'loss']
    workloads = []
    for profile in (1, 2, 3):
        for kind in ('sequential', 'permuted', 'conflict', 'expanded'):
            chosen = [r for r in comparisons if r['profile'] == profile and r['family'] == 'path'
                      and r['group'] == 'primary' and r['depth'] == 2 and r['early'] == 1
                      and (r['N'], r['S']) == (8, 3) and r['workload'] == kind]
            require(len(chosen) == 4, 'Workload comparison must contain four traces')
            workloads.append(dict(profile=profile, workload=kind,
                **{label + '_rate_mean': statistics.mean(r[label + '_rate'] for r in chosen) for label in 'ABH'},
                H_vs_A=counts(r['H_vs_A'] for r in chosen), H_vs_B=counts(r['H_vs_B'] for r in chosen)))
    summary = dict(passed=True, schema_version=1, evaluation='Stage 6 analysis of preserved native RTL evidence',
        provenance=provenance, cohorts=cohorts, depth_outcomes=counts(r['outcome'] for r in depths),
        depth_regressions=regressions, window_flips=flips,
        early_controls=[dict(depth=depth, pairs=sum(r['depth'] == depth for r in controls),
            outcomes=counts(r['outcome'] for r in controls if r['depth'] == depth)) for depth in (1, 2)],
        default=[paired['default', depth] for depth in (1, 2)],
        workload_example=workloads,
        request_skew=[paired['request_skew', depth] for depth in (1, 2)],
        tail_example=[paired['path_p2_n32_s8_sequential_seed11_early1', depth] for depth in (1, 2)],
        limitations=['Exploratory simulation timings; no calibrated hardware, synthesis, timing closure or resource utilization.',
                    'Both source stores contain the complete immutable 256 KiB fixture; placement/preload/update costs excluded.',
                    'Equal assembly storage at each depth does not imply equal interface or source-memory cost.',
                    'Four trace ranges are descriptive, not confidence intervals or win probabilities.',
                    'Command-relative latency starts at admission; application release-to-completion latency is not measured.'])
    return summary, comparisons, depths, controls, ranges


def csv_text(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def markdown(summary):
    def wtl(value):
        return '/'.join(str(value[key]) for key in ('win', 'tie', 'loss'))
    lines = ['# Core evaluation: matched native RTL evidence', '',
        'Generated by `python3 benchmarks/report_core.py`. All 2,616 saved native runs were re-accounted; '
        'all 1,308 depth-one records match shared historical fields. This is a new analysis, not a new simulation campaign.', '',
        '## Hybrid against both baselines at equal capacity', '',
        '| Profile / cohort | Slots | Cases | H vs A W/T/L | H vs B W/T/L | Beats both |',
        '| --- | ---: | ---: | --- | --- | ---: |']
    names = ['P0 primary', 'P1 quiet, recommended sequential', 'P2 reservations, recommended sequential', 'P3 shared, recommended sequential']
    for row in summary['cohorts']:
        lines.append(f'| {names[row["profile"]]} | {row["depth"]} | {row["cases"]} | '
                     f'{wtl(row["H_vs_A"])} | {wtl(row["H_vs_B"])} | {row["beats_both"]} |')
    lines += ['', 'P1–P3 use early delivery on, six fixed geometry/split choices and four traces. '
        'Counts describe these cases, not probabilities. Aggregate-rate controls remain outside the primary cohorts.', '',
        '## P0 default: capacity and admission latency', '',
        '| Slots | Mode | Words/cycle | Startup first | Mean command→first | Mean command→complete | p99 complete |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for row in summary['default']:
        for label, mode in zip('ABH', MODES):
            lines.append(f'| {row["depth"]} | {mode} | {row[label+"_rate"]:.6f} | {row[label+"_startup_first"]} | '
                f'{row[label+"_command_first_mean"]:.3f} | {row[label+"_command_complete_mean"]:.3f} | {row[label+"_command_complete_p99"]} |')
    lines += ['', 'Two slots accept work sooner, so acceptance-relative latency includes additional queue waiting. '
        'It is not an application release-to-completion metric. Logical assembly data doubles from N×32 to 2N×32 bits, '
        'plus output registers and metadata, in every mode. Hybrid still uses two source interfaces.', '',
        '## Workload sensitivity at a fixed geometry', '',
        'N=8, S=3, two slots, early on; rates are means across the four fixed traces. '
        'Each W/T/L comparison is made within the same trace. Permuted access preserves the sequential footprint; '
        'conflict and expanded access are separately constructed locality stressors.', '',
        '| Profile | Workload | A rate | B rate | H rate | H vs A W/T/L | H vs B W/T/L |',
        '| --- | --- | ---: | ---: | ---: | --- | --- |']
    for row in summary['workload_example']:
        lines.append(f'| P{row["profile"]} | {row["workload"]} | {row["A_rate_mean"]:.6f} | '
                     f'{row["B_rate_mean"]:.6f} | {row["H_rate_mean"]:.6f} | '
                     f'{wtl(row["H_vs_A"])} | {wtl(row["H_vs_B"])} |')
    lines += ['',
        '## Every depth regression', '',
        f'Across 1,308 within-mode comparisons: {wtl(summary["depth_outcomes"])} faster/tie/slower. '
        'These counts combine labeled configurations only to describe the capacity experiment; they are not an overall speedup.', '',
        '| Case | Mode | One-slot cycles | Two-slot cycles | Extra cycles |',
        '| --- | --- | ---: | ---: | ---: |']
    for row in summary['depth_regressions']:
        lines.append(f'| {row["case"]} | {row["mode"]} | {row["one_cycles"]} | {row["two_cycles"]} | {row["delta_cycles"]} |')
    lines += ['', '## Every doubled-window ranking flip', '',
        '| Case | Slots | Baseline | Standard window | Doubled window |', '| --- | ---: | --- | --- | --- |']
    for row in summary['window_flips']:
        lines.append(f'| {row["case"]} | {row["depth"]} | {row["baseline"]} | {row["short"]} | {row["long"]} |')
    lines += ['', '## Early delivery on versus full-block wait', '',
        '| Slots | Paired mode/configurations | Faster / tie / slower |', '| --- | ---: | --- |']
    for row in summary['early_controls']:
        lines.append(f'| {row["depth"]} | {row["pairs"]} | {wtl(row["outcomes"])} |')
    lines += ['', 'Throughput ties can retain first-word benefits. Consult [all early controls](core-early-controls.csv). '
        'A finite-window loss is retained, even when small.', '',
        '## Mean throughput and tail latency can disagree', '',
        'P2, N=32, S=8, trace 11, early delivery on:', '',
        '| Slots | Mode | Words/cycle | Mean command→complete | p99 command→complete |',
        '| --- | --- | ---: | ---: | ---: |']
    for row in summary['tail_example']:
        for label, mode in zip('ABH', MODES):
            lines.append(f'| {row["depth"]} | {mode} | {row[label+"_rate"]:.6f} | '
                         f'{row[label+"_command_complete_mean"]:.3f} | {row[label+"_command_complete_p99"]} |')
    lines += ['', '## Full evidence and interpretation', '',
        '- [872 matched case/depth comparisons](core-comparisons.csv), including min/median/mean/p95/p99/max '
        'command- and request-relative first/completion times, both baselines and raw-record paths.',
        '- [All 1,308 depth comparisons](core-depth-effects.csv), [all early controls](core-early-controls.csv), '
        'and [declared-trace ranges](core-trace-ranges.csv), with workload/split/profile/group preserved '
        '(four traces except the separately labeled one-trace slow-sink controls).',
        '- [Audited summary and source/input/report hashes](core-summary.json); [narrative conclusions](../docs/stage6-results.md).', '',
        '## Limits', '']
    lines += ['- ' + limit for limit in summary['limitations']]
    return '\n'.join(lines) + '\n'


def products(summary, comparisons, depths, controls, ranges):
    return {'core-summary.json': json_text(summary), 'core-results.md': markdown(summary),
            'core-comparisons.csv': csv_text(comparisons), 'core-depth-effects.csv': csv_text(depths),
            'core-early-controls.csv': csv_text(controls), 'core-trace-ranges.csv': csv_text(ranges)}


def plot(summary, comparisons):
    os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'build/matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10, 'axes.spines.top': False,
                         'axes.spines.right': False, 'svg.hashsalt': 'fpga-core-stage6'})
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.2), layout='constrained')
    colors = ['#286291', '#D18135', '#17836B']
    ax = axes[0, 0]
    for j, (label, mode, color) in enumerate(zip('ABH', MODES, colors)):
        values = [row[label + '_rate'] for row in summary['default']]
        x = [j - .18, j + .18]
        ax.bar(x, values, width=.32, color=color, alpha=.85)
        for xp, value in zip(x, values):
            ax.text(xp, value + .025, f'{value:.3f}', ha='center', fontsize=9)
    ax.set_xticks(range(3), MODES)
    ax.set_ylim(0, 1.03)
    ax.set_ylabel('Delivered words / cycle')
    ax.set_title('P0 default · equal capacity per comparison\nLeft: one slot   Right: two slots', loc='left', fontsize=12)
    ax.grid(axis='y', alpha=.18)
    splits = [(8, 1), (8, 3), (8, 7), (32, 8), (32, 24), (256, 64)]
    for profile, ax in zip((1, 2, 3), (axes[0, 1], axes[1, 0], axes[1, 1])):
        for depth, color, marker in [(1, '#7A8797', 'o'), (2, '#176B62', 's')]:
            means, low, high = [], [], []
            for n, split in splits:
                values = [row['H_over_best_rate'] for row in comparisons if row['profile'] == profile
                          and row['family'] == 'path' and row['group'] == 'primary' and row['workload'] == 'sequential'
                          and row['early'] == 1 and row['depth'] == depth and (row['N'], row['S']) == (n, split)]
                require(len(values) == 4, 'Plot must contain four traces per point')
                mean = statistics.mean(values)
                means.append(mean); low.append(mean - min(values)); high.append(max(values) - mean)
            x = [i + (depth - 1.5) * .13 for i in range(len(splits))]
            ax.errorbar(x, means, yerr=[low, high], color=color, marker=marker, capsize=3,
                        linewidth=1.5, label=f'{depth} slot' + ('s' if depth == 2 else ''))
        ax.axhline(1, color='#C07B34', linestyle='--', linewidth=1.2)
        ax.text(5.25, 1.015, 'better baseline', ha='right', fontsize=8, color='#92551A')
        ax.set_xticks(range(6), [f'{n}/{split}' for n, split in splits])
        ax.set_ylim(.1, 1.3)
        ax.set_ylabel('Hybrid throughput / better baseline')
        ax.set_xlabel('Block words / A-prefix words')
        ax.set_title({1: 'P1 quiet · full-rate resident A wins', 2: 'P2 local reservations · split matters',
                      3: 'P3 shared return · service limits matter'}[profile], loc='left', fontsize=12)
        ax.grid(axis='y', alpha=.18)
        ax.legend(loc='lower right', frameon=False)
    fig.suptitle('Split-memory streaming: measured tradeoffs, not a universal speedup\n'
                 'Native RTL · matched A-only / B-only / hybrid · recommended sequential, early delivery on', fontsize=15)
    fig.supxlabel('P1–P3 points: means across four fixed traces; whiskers: min–max, not confidence intervals.\n'
                  'Exploratory simulation timings. Equal assembly capacity does not imply equal interface cost.', fontsize=9)
    for extension in ('png', 'svg'):
        metadata = {'Software': 'Matplotlib'} if extension == 'png' else {'Date': None}
        fig.savefig(ROOT / f'results/core-overview.{extension}', dpi=180, metadata=metadata)
    plt.close(fig)
    (ROOT / 'results/core-plots.json').write_text(json_text(dict(
        summary_sha256=digest(ROOT / 'results/core-summary.json'),
        script_sha256=digest(Path(__file__)), matplotlib=matplotlib.__version__,
        artifacts={f'core-overview.{ext}': digest(ROOT / f'results/core-overview.{ext}') for ext in ('png', 'svg')})))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Audit and verify committed reports without writing them')
    parser.add_argument('--plots', action='store_true', help='Generate PNG/SVG using the optional plotting environment')
    args = parser.parse_args()
    require(not (args.check and args.plots), '--check is read-only; omit --plots')
    report, lookup, provenance = audit()
    analyzed = analyze(report, lookup, provenance)
    for name, text in products(*analyzed).items():
        path = ROOT / 'results' / name
        if args.check:
            require(path.read_text() == text, 'Generated report is stale: ' + name)
        else:
            path.write_text(text)
    if args.plots:
        plot(analyzed[0], analyzed[1])
    print('PASS Stage 6: 2616 recomputed metric sets; 1308 historical matches; '
          f'{len(analyzed[0]["depth_regressions"])} depth regressions and '
          f'{len(analyzed[0]["window_flips"])} window flips retained', flush=True)


if __name__ == '__main__':
    try:
        main()
    except (AuditError, OSError, KeyError, ValueError) as error:
        print('FAIL Stage 6 audit:', error, file=sys.stderr)
        raise SystemExit(1)
