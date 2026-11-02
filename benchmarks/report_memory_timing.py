#!/usr/bin/env python3
"""Reports only checked native RTL results; no performance simulation here."""
import csv, hashlib, json, statistics
from collections import Counter,defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'results/raw/memory_timing'

def table(headers,rows):
    return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+''.join('| '+' | '.join(map(str,row))+' |\n' for row in rows)+'\n'
def fmt(x):return f'{x:.6f}'
def verdict(c):return c['steady_H_vs_A']+'/'+c['steady_H_vs_B']
def main():
    report=json.loads((OUT/'summary.json').read_text());assert report['passed'] and len(report['runs'])==1230
    replay=json.loads((OUT/'p0-equivalence.json').read_text());assert replay['passed']
    comps=report['comparisons'];runs=report['runs'];bycase=defaultdict(dict)
    flat=[]
    for r in runs:
        c,m=r['case'],r['metrics'];bycase[c['name']][r['mode']]=r
        row={k:c[k] for k in ['name','family','group','profile','seed','N','S','early','workload','warmup','measured']}
        row.update(mode=r['mode'],whole_intervals=m['whole_intervals'],startup_first=m['startup_first'])
        row.update({f'steady_{k}':v for k,v in m['steady'].items()})
        for label,values in m['latency'].items():
            for stat,v in values.items():row[f'{label}_{stat}']=v
        for stat,v in m['window32_stats'].items():row[f'window32_rate_{stat}']=v
        row.update(r['config']);flat.append(row)
    columns=list(dict.fromkeys(k for row in flat for k in row))
    with (ROOT/'results/memory-timing-metrics.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(flat)
    groups=defaultdict(list)
    for c in comps:
        if c['family']=='path':
            key=tuple(c[k] for k in ['profile','N','S','early','workload','group'])
            groups[key].append(c)
    variability=[]
    for key,cs in groups.items():
        row=dict(zip(['profile','N','S','early','workload','group'],key));row['traces']=len(cs)
        for mode in 'ABH':
            values=[c[mode+'_rate'] for c in cs]
            row.update({mode+'_min':min(values),mode+'_median':statistics.median(values),mode+'_max':max(values)})
        for baseline in 'AB':
            for outcome in ('win','tie','loss'):
                row[f'H_vs_{baseline}_{outcome}']=sum(c['steady_H_vs_'+baseline]==outcome for c in cs)
        variability.append(row)
    with (ROOT/'results/memory-timing-variability.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(variability[0]));w.writeheader();w.writerows(variability)
    lines=['# Memory timing: checked RTL results\n',
           'The approved simulation-only extension is complete. P0 was replayed in **78 runs**, with byte-identical per-block records and exactly equal metrics. The new models passed **1,230 performance runs / 410 matched triplets** after verification. Stage 4 and automatic selection remain unimplemented.\n',
           'All numeric timing settings are exploratory normalized cycles. A is interpreted as a local SRAM scratchpad and B as an HBM-backed adapter; the entire immutable 256 KiB fixture is resident in both sources before measurement. Preload cost is excluded. These experiments provide no physical FPGA/HBM performance, area, clock, power or BRAM-inference evidence. See the [approved proposal](memory-timing-proposal.md) for authoritative mechanism references and their limits.\n',
           '## Validation and reference preservation\n',
           '- Original 36 baseline/model + 32 hybrid outcomes pass; original smoke and eight measurement tests pass.\n- Strict lint passes for all seven tops.\n- New model suite: 28 outcomes: 16 positive cases and 12 named expected failures (four trace-file errors and eight protocol/grant faults).\n- New controller integration suite: 31 outcomes, including all modes/early settings/four traces, shared reset with a witnessed held output, and the hand-derived grant/output example. Eight new measurement tests include seven deliberate raw-record mutations.\n',
           'The fixed service example grants A/B/A/B at normalized edges 1/3/4/5; response writes are 2/4/5/6 and controller consumption is 4/7/8/9. Isolated B first-response latencies for the directed closed/hit/conflict/bank/crossing sequence are 14/2/26/14/26/2/14. A setup interrupted by maintenance accepts at edge 20 and responds at edge 76 in its fixed reserved-fabric calendar. These are simulated checks against hand-written expectations.\n',
           'No controller, bank, address scoreboard, original model, original benchmark harness/runner, or historical result was changed. The saved reference manifest checks 212 files. Fresh P0 evidence is under `results/raw/memory_timing/p0/`; all new-profile records/configurations/logs are separate.\n',
           '## Fairness and measurement\n',
           'Each triplet uses the same ordered command addresses, sink readiness, reset origin and finite external calendar files. Disturbance seeds are 11/29/47/83; address order uses fixed workload seed 7. Jitter is sampled at actual request acceptance, so different acceptance times legitimately encounter different conditions. Row and arbitration histories follow each mode’s requests. P3 grants one available word per edge, with work-conserving beat round robin; an unused interface does not reserve half the link. Held responses may handshake on reserved transport edges.\n',
           'The [predeclared matrix](memory-timing-execution-plan.md) reduces the address-pattern/slow-sink cross product before execution. Legacy overlays preserve each old L/I/K/G/C/acceptance/sink setting; recommended-path runs use A L2/I1 and B L48/I1/K16/G2. Names such as equal_fast mean equal base parameters in overlays, not equal resulting paths. The aggregate-rate control is supplementary and denotes nominal input rates only after reservations.\n',
           'Whole intervals are final consumption minus first command acceptance. Whole rate uses the inclusive edge-count window; steady rate uses the 1,024 measured blocks after 64 warmup blocks (or the labeled doubled/short controls). Integer cycle counts determine exact wins/ties/losses. First-word and completion distributions are command-relative; request-relative first valid, first handshake and completion are also retained. Output readiness partitions, occupancy, per-path grants/responses, reserved capacity, row events and pause episodes are logged. Reservations are unavailable capacity, not completed external traffic. Four traces and correlated blocks do not support confidence-interval claims.\n',
           '## Paired outcomes against both baselines\n']
    rows=[]
    for family in ['legacy','path']:
        for p in (1,2,3):
            cs=[c for c in comps if c['family']==family and c['profile']==p and c['group']=='primary'
                and (family=='legacy' or (c['early']==1 and c['workload']=='sequential'))]
            for window in ('whole','steady'):
                a=Counter(c[f'{window}_H_vs_A'] for c in cs);b=Counter(c[f'{window}_H_vs_B'] for c in cs)
                both=sum(c[f'{window}_H_vs_A']=='win' and c[f'{window}_H_vs_B']=='win' for c in cs)
                losses=sum(c[f'{window}_H_vs_A']=='loss' and c[f'{window}_H_vs_B']=='loss' for c in cs)
                rows.append([family,f'P{p}',window,len(cs),f'{a["win"]}/{a["tie"]}/{a["loss"]}',f'{b["win"]}/{b["tie"]}/{b["loss"]}',both,losses])
    lines.append(table(['Family','Profile','Window','Triplets','vs A W/T/L','vs B W/T/L','Beats both','Loses both'],rows))
    lines.append('Legacy counts use the same 20 primary cases at seed 11. Path counts use six splits × four traces, sequential, early delivery on. Counts describe these sampled cases, not probabilities. Endpoint ties are included in the legacy matrix.\n')
    lines.append('## Recommended settings: split, latency and variability\n')
    rows=[]
    for v in variability:
        if v['group']=='primary' and v['workload']=='sequential' and v['early']==1:
            rows.append([f'P{v["profile"]}',f'{v["N"]}/{v["S"]}',
                         *[f'{v[k+"_median"]:.6f} [{v[k+"_min"]:.6f},{v[k+"_max"]:.6f}]' for k in 'ABH'],
                         f'{v["H_vs_A_win"]}/{v["H_vs_A_tie"]}/{v["H_vs_A_loss"]}',
                         f'{v["H_vs_B_win"]}/{v["H_vs_B_tie"]}/{v["H_vs_B_loss"]}'])
    lines.append(table(['Profile','N/S','A rate median [range]','B rate median [range]','Hybrid rate median [range]','vs A W/T/L','vs B W/T/L'],rows))
    lines.append('Rates are words per simulated cycle. Complete paired per-trace classifications are in [comparison CSV](../results/raw/memory_timing/summary.csv); every distribution and configuration is in [flat metrics](../results/memory-timing-metrics.csv), and all four-trace ranges in [variability CSV](../results/memory-timing-variability.csv).\n')
    rows=[]
    for p in (1,2,3):
        name=f'path_p{p}_n8_s3_sequential_seed11_early1'
        for mode in old_modes():
            m=bycase[name][mode]['metrics'];first=m['latency']['command_first'];complete=m['latency']['command_complete']
            rows.append([f'P{p}',mode,first['min'],round(first['mean'],3),first['p95'],first['p99'],first['max'],
                         round(complete['mean'],3),complete['p95'],complete['p99'],complete['max'],
                         fmt(m['steady']['words_per_cycle']),f'{m["window32_stats"]["min"]:.6f}–{m["window32_stats"]["max"]:.6f}'])
    lines.append(table(['Profile','Mode','First min','First mean','p95','p99','max','Complete mean','p95','p99','max','Steady rate','32-block rate range'],rows))
    lines.append('This latency table fixes N=8,S=3, seed 11, sequential, early on. Medians and all request-relative statistics are retained in the CSV/JSON. It is a representative display, not a substitute for the full matrix.\n')
    lines.append('## Early-delivery, locality and window controls\n')
    rows=[]
    for p in (1,2,3):
        for kind in ['sequential','permuted','conflict','expanded']:
            for early in (1,0):
                v=next(v for v in variability if (v['profile'],v['N'],v['S'],v['early'],v['workload'],v['group'])==(p,8,3,early,kind,'primary'))
                rows.append([f'P{p}',kind,early,*[fmt(v[m+'_median']) for m in 'ABH'],
                             f'{v["H_vs_A_win"]}/{v["H_vs_A_tie"]}/{v["H_vs_A_loss"]}',f'{v["H_vs_B_win"]}/{v["H_vs_B_tie"]}/{v["H_vs_B_loss"]}'])
    lines.append(table(['Profile','Address stream','Early','A median rate','B median rate','Hybrid median rate','vs A W/T/L','vs B W/T/L'],rows))
    long=[c for c in comps if c['family']=='path' and c['group']=='sensitivity'];changes=[];maxdelta=0
    for c in long:
        other=next(x for x in comps if x['case']==c['case'].removesuffix('_long'))
        for mode in 'ABH':maxdelta=max(maxdelta,abs(c[mode+'_rate']-other[mode+'_rate']))
        if verdict(c)!=verdict(other):changes.append(c['case'])
    lines.append(f'Doubling warmup/measurement to 128/2,048 changes paired steady classifications in **{len(changes)}/{len(long)}** representative triplets; maximum absolute mode-rate change is {maxdelta:.6f} words/cycle. Changed cases: '+(', '.join(changes) if changes else 'none')+'.\n')
    paused=[r for r in runs if r['case']['profile']>=2 and r['case']['group']!='short']
    zero=[r['case']['name']+'/'+r['mode'] for r in paused if r['metrics']['steady']['pause_episodes']==0]
    lines.append(f'Among {len(paused)} non-short P2/P3 runs, {len(zero)} steady windows contain no maintenance-start episode. Counts are retained per run; this does not require an A-only run to use B. Short startup runs are deliberately not evidence of steady pause behavior.\n')
    if zero:lines.append('Zero-start windows: '+', '.join(zero)+'.\n')
    lines.append('## Which historical conclusions survive?\n')
    specs=[('S=1 beats both','split_1','win/win'),('S=3 ties B completion','default','tie B; early first vs B'),
           ('Long A prefix loses to B','large_prefix24','loss vs B'),('Slow sink ties both','slow_sink','tie/tie'),
           ('Nominal aggregate-rate control loses both','aggregate_rate_control','loss/loss'),
           ('Request skew gives only a 3-edge startup win vs B','request_skew','steady tie B; whole win B')]
    rows=[]
    for title,name,original in specs:
        cs=[next(c for c in comps if c['case']==f'legacy_p{p}_{name}') for p in (1,2,3)]
        values=[f'{verdict(c)}; H={c["H_rate"]:.6f}' for c in cs]
        rows.append([title,original,*values])
    lines.append(table(['Previous finding','P0','P1 steady vs A/B','P2 steady vs A/B','P3 steady vs A/B'],rows))
    lines.append('The explicit survival verdicts, mechanisms, review questions and next decision are in the [checkpoint interpretation](memory-timing-interpretation.md). This table retains original parameters so changed behavior can be attributed to jitter, row/setup, burst boundaries, reservations and sharing. The recommended-setting tables additionally change A to full offered bandwidth and B to a longer adapter latency; those are separate experiments.\n')
    lines.append('## Model contract and limits\n')
    lines.append('The pair owns one descriptor and one response register per interface. Grants fill/replace registers; valid/data/last remain stable through pauses and sink stalls. Request ownership ends only on the final response handshake. B has four row tags; row setup adds 12 closed or 24 conflict cycles, with absolute 16-word chunk boundaries and maintenance invalidation/restart. Shared reset clears ownership, row state, held validity, deadlines, arbitration and calendar epoch. The unchanged assembly banks still use synchronous reads: a response written at w can be consumed no earlier than w+2. The address-only scoreboard receives no split, timing, grant or row state.\n')
    lines.append('The finite calendar is saved as explicit jitter samples plus a lossless periodic-event encoding, checked for malformed data and exhaustion. Calendar opportunity bounds and seeds are recorded. No native HBM commands, width conversion, overfetch, bank-group limits, deep queues, cache effects, external same-bank row pollution, live replication cost or vendor-controller ordering are modeled. The public-channel monitor checks conservation/capacity/timing bounds separately from end-to-end data. Directed tests and four exogenous schedules do not prove every possible scheduler or complete Stage 5.\n')
    lines.append('## Artifacts\n')
    lines.append('![Split comparisons](../results/memory-timing-splits.png)\n')
    lines.append('- [Full native-run manifest and metrics](../results/raw/memory_timing/summary.json)\n- [Paired comparisons](../results/raw/memory_timing/summary.csv)\n- [Per-run flat metrics](../results/memory-timing-metrics.csv) and [trace variability](../results/memory-timing-variability.csv)\n- [P0 exact replay proof](../results/raw/memory_timing/p0-equivalence.json)\n- Per-block CSVs and native logs under `results/raw/memory_timing/runs/`; input files/hashes under `inputs/`; verification evidence under `docs/validation/memory-timing/`.\n')
    (ROOT/'docs/memory-timing-results.md').write_text('\n'.join(lines))
    (OUT/'report-metadata.json').write_text(json.dumps(dict(passed=True,runs=len(runs),triplets=len(comps),
        source_sha256=hashlib.sha256((Path(__file__)).read_bytes()).hexdigest(),summary_sha256=hashlib.sha256((OUT/'summary.json').read_bytes()).hexdigest()),indent=2)+'\n')
    print('PASS reports generated:',len(runs),'runs',len(variability),'variability groups')
def old_modes():return ['A-only','B-only','hybrid']
if __name__=='__main__':main()
