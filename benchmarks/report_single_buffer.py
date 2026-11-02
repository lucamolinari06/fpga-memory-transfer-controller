#!/usr/bin/env python3
"""Create review tables and a flat metrics CSV from the saved successful sweep."""
from collections import Counter
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
report = json.loads((ROOT/'results/raw/single_buffer/summary.json').read_text())
assert report['passed'] and report['scope'] == 'full'
comparisons = report['comparisons']
primary = [r for r in comparisons if r['group'] == 'primary']

def table(headers, rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |'] +
                     ['| '+' | '.join(str(x) for x in row)+' |' for row in rows])+'\n\n'

def run(case, mode):
    return next(r for r in report['runs'] if r['case']['name']==case and r['mode']==mode)

lines = ['# Executed single-buffer benchmark tables\n',
         'Generated from `raw/single_buffer/summary.json`; all measurements are architectural cycles or 32-bit words/cycle. Full per-block CSVs and run logs are under `raw/single_buffer/`.\n',
         '## Matched primary configurations\n',
         'Defaults: N=8,S=3; A: L=2,I=3,K=256,G=0,C=0, acceptance=1/1; B: L=6,I=1,K=256,G=0,C=0, acceptance=1/1. Sink=1/1 ready, no fixed stall. Every row uses 64 warmup + 1,024 measured blocks, early delivery enabled, one slot. L/I/G/C are cycles; K is words. All three modes within a row receive the same full configuration.\n']
default = run('default','A-only')['config']
lines.append(table(['Case','N','S','Changes from default'],[(r['case'],r['N'],r['S'],
    ', '.join(f'{k}={v}' for k,v in run(r['case'],'A-only')['config'].items() if v != default[k]) or 'none') for r in primary]))
lines += ['## Whole workload: exact win/tie/loss\n',
          'Elapsed intervals from first command to final consumption, including all 1,088 blocks. Ratio is baseline/hybrid; >1 favors hybrid. Classifications use exact integers, not rounded ratios.\n',
          table(['Case','A cycles','B cycles','Hybrid cycles','H vs A','H vs B','A/H','B/H'],
                [(r['case'],r['A_cycles'],r['B_cycles'],r['H_cycles'],r['H_vs_A'],r['H_vs_B'],
                  f"{r['A_over_H']:.4f}",f"{r['B_over_H']:.4f}") for r in primary])]
counts = {baseline:dict(Counter(r[f'H_vs_{baseline}'] for r in primary)) for baseline in ['A','B']}
lines.append(f'Directed-case totals (not probabilities): `{json.dumps(counts,sort_keys=True)}`.\n')
lines += ['## Steady throughput\n',
          'Each mode uses its own completion-delimited window `(d_63,d_1087]` for the same measured work. Sink/request readiness still follows the same reset-relative clock. All gaps are counted.\n',
          table(['Case','A words/cycle','B words/cycle','Hybrid words/cycle','Steady H vs A','Steady H vs B'],
                [(r['case'],f"{r['A_rate']:.6f}",f"{r['B_rate']:.6f}",f"{r['H_rate']:.6f}",
                  r['steady_H_vs_A'],r['steady_H_vs_B']) for r in primary])]
lines += ['## First-word latency\n',
          'Mean command-to-first-consumption intervals over the 1,024 measured blocks. Min/p95/max and request-based metrics remain in the JSON/flat CSV.\n',
          table(['Case','A first','B first','Hybrid first'],
                [(r['case'],*[f"{run(r['case'],mode)['metrics']['latency']['command_first']['mean']:.3f}" for mode in ['A-only','B-only','hybrid']]) for r in primary])]
lines += ['## Separate controls\n',
          'Gated rows use EARLY_DELIVERY=0 in all three modes; default_gated and slow_sink_gated otherwise match their primary namesakes. Aggregate-rate control uses N=32,S=16,L_A=L_B=2,G=C=0: baselines I=1, hybrid I_A=I_B=2. It changes hybrid memory settings and is deliberately excluded from primary win totals. Short_default uses 1 warmup + 1 measured block. Long_window cases use 128+2,048 blocks.\n',
          table(['Case','Group','A cycles','B cycles','H cycles','H vs A','H vs B','A rate','B rate','H rate'],
                [(r['case'],r['group'],r['A_cycles'],r['B_cycles'],r['H_cycles'],r['H_vs_A'],r['H_vs_B'],
                  f"{r['A_rate']:.6f}",f"{r['B_rate']:.6f}",f"{r['H_rate']:.6f}") for r in comparisons if r['group']!='primary'])]
lines += ['## Default steady counters and occupancy\n',
          table(['Metric','A-only','B-only','Hybrid'],
                [(key,*[run('default',mode)['metrics']['steady'][key] for mode in ['A-only','B-only','hybrid']])
                 for key in ['cycles','useful','unavailable','intentional','held','slot_average','slot_max',
                             'backlog_average','backlog_max','early_words','a_requests','b_requests','a_beats','b_beats',
                             'a_accepted_rate','b_accepted_rate','a_busy_service_rate','b_busy_service_rate']])]
(ROOT/'results/single-buffer-tables.md').write_text('\n'.join(lines))

def flatten(obj,prefix=''):
    result = {}
    for k,v in obj.items():
        name = prefix+k
        if isinstance(v,dict): result.update(flatten(v,name+'.'))
        else: result[name] = v
    return result

rows = []
for r in report['runs']:
    rows.append(dict(case=r['case']['name'],group=r['case']['group'],mode=r['mode'],N=r['case']['N'],S=r['case']['S'],
                     warmup=r['case']['warmup'],measured=r['case']['measured'],early=r['case']['early'],
                     **flatten(r['config'],'config.'),**flatten(r['metrics'],'metrics.')))
with (ROOT/'results/single-buffer-metrics.csv').open('w') as stream:
    writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
    writer.writeheader(); writer.writerows(rows)
print(f'Generated review tables and flat metrics for {len(rows)} successful runs')
