#!/usr/bin/env python3
"""Audit and report matched native RTL observations; no simulated DUT in Python."""
import collections,csv,hashlib,json
from pathlib import Path
import run_double_buffer as b
ROOT=b.ROOT

def main():
    report=json.loads((b.OUT/'summary.json').read_text());assert report['passed'] and report['scope']=='full' and len(report['runs'])==2616
    assert report['source_sha256']==b.old.hashes(report['source_sha256'])
    runs=report['runs'];lookup={};paired=[];flat=[]
    for r in runs:
        assert r['source_sha256']==report['source_sha256'] and r['passed']
        assert hashlib.sha256((ROOT/r['records']).read_bytes()).hexdigest()==r['records_sha256']
        for p,digest in r['input_sha256'].items():
            if p=='dataset':assert digest==report['fixture_sha256']
            else:assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest
        key=(r['case']['name'],r['depth'],r['mode']);assert key not in lookup;lookup[key]=r
        c=r['case'];m=r['metrics']
        f=dict(case=c['name'],family=c['family'],group=c['group'],profile=c['profile'],seed=c['seed'],N=c['N'],S=c['S'],early=c['early'],workload=c['workload'],depth=r['depth'],mode=r['mode'],whole_intervals=m['whole_intervals'],startup_first=m['startup_first'])
        f.update({'steady_'+k:v for k,v in m['steady'].items()})
        f.update({'window32_'+k:v for k,v in m['window32_stats'].items()})
        expected=dict(c['args'])
        if c['group']=='rate_control' and r['mode']=='hybrid':expected.update(a_interval=2,b_interval=2)
        assert r['config']==expected
        for k,v in m['latency'].items():
            for stat,value in v.items():f[k+'_'+stat]=value
        flat.append(f)
    for c in b.matrix():
        members=[lookup[c['name'],d,mode] for d in [1,2] for mode in b.old.MODES]
        assert all(r['case']==c for r in members)
        assert len({json.dumps(r['input_sha256'],sort_keys=True) for r in members})==1
        for d in [1,2]:
            a,bb,h=[lookup[c['name'],d,mode]['metrics'] for mode in b.old.MODES]
            row=dict(case=c['name'],family=c['family'],group=c['group'],profile=c['profile'],seed=c['seed'],N=c['N'],S=c['S'],early=c['early'],workload=c['workload'],depth=d)
            for label,m in zip('ABH',[a,bb,h]):
                row[label+'_cycles']=m['steady']['cycles'];row[label+'_rate']=m['steady']['words_per_cycle']
                row[label+'_first_mean']=m['latency']['command_first']['mean'];row[label+'_complete_mean']=m['latency']['command_complete']['mean'];row[label+'_complete_p99']=m['latency']['command_complete']['p99']
            for label,m in [('A',a),('B',bb)]:
                row['steady_H_vs_'+label]=b.old.outcome(h['steady']['cycles'],m['steady']['cycles'])
                row['whole_H_vs_'+label]=b.old.outcome(h['whole_intervals'],m['whole_intervals'])
            paired.append(row)
        if c['S'] in (0,c['N']):
            baseline='B-only' if c['S']==0 else 'A-only'
            for d in [1,2]:assert lookup[c['name'],d,'hybrid']['metrics']==lookup[c['name'],d,baseline]['metrics'],'Endpoint mismatch'
    def csvwrite(name,data):
        keys=list(dict.fromkeys(k for row in data for k in row))
        with (ROOT/'results'/name).open('w') as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(data)
    csvwrite('double-buffer-metrics.csv',flat);csvwrite('double-buffer-comparisons.csv',paired)
    def wtl(rows,key):
        counts=collections.Counter(r[key] for r in rows);return '/'.join(str(counts[k]) for k in ['win','tie','loss'])
    text=['# Stage 4 matched RTL results','', 'All 2,616 runs pass: 436 configurations × three modes × two buffer capacities. Every depth-one run matches every shared historical per-block field exactly and compares public channels to the original controller each edge. Figures below are simulation cycles and words per cycle under exploratory settings.','', '## Hybrid against both baselines at equal capacity','', '| Group | Depth | Cases | H vs A W/T/L | H vs B W/T/L | Beats both |','| --- | ---: | ---: | --- | --- | ---: |']
    for group,p in [('P0 primary',0),('P1 recommended sequential early-on',1),('P2 recommended sequential early-on',2),('P3 recommended sequential early-on',3)]:
        for d in [1,2]:
            chosen=[r for r in paired if r['profile']==p and r['depth']==d and ((p==0 and r['group']=='primary') or (p>0 and r['family']=='path' and r['group']=='primary' and r['workload']=='sequential' and r['early']==1))]
            both=sum(r['steady_H_vs_A']==r['steady_H_vs_B']=='win' for r in chosen)
            text.append(f'| {group} | {d} | {len(chosen)} | {wtl(chosen,"steady_H_vs_A")} | {wtl(chosen,"steady_H_vs_B")} | {both} |')
    text+=['','Counts describe sampled cases, not probabilities. Supplementary rate controls, slow sinks, early-off, scattered workloads and window controls remain in the complete comparison CSV and are excluded from this selected table.','', '## Two slots versus one within each mode','', '| Profile | Mode | Cases | Faster / tie / slower |','| --- | --- | ---: | --- |']
    effects=[]
    for c in b.matrix():
        for mode in b.old.MODES:
            one,two=[lookup[c['name'],d,mode]['metrics'] for d in [1,2]]
            effects.append(dict(case=c['name'],profile=c['profile'],group=c['group'],mode=mode,outcome=b.old.outcome(two['steady']['cycles'],one['steady']['cycles']),speedup=one['steady']['cycles']/two['steady']['cycles'],one_cycles=one['steady']['cycles'],two_cycles=two['steady']['cycles']))
    for p in range(4):
        for mode in b.old.MODES:
            selected=[r for r in effects if r['profile']==p and r['mode']==mode]
            text.append(f'| P{p} | {mode} | {len(selected)} | {wtl(selected,"outcome")} |')
    csvwrite('double-buffer-depth-effects.csv',effects)
    text+=['','This comparison explicitly doubles assembly storage from N×32 to 2N×32 data bits for every mode. Interface outstanding limits, memory capacity and shared service limits remain unchanged. Hybrid still has two source interfaces.','', '## Selected cases','', '| Case | Depth | A rate | B rate | H rate | H vs A | H vs B |','| --- | ---: | ---: | ---: | ---: | --- | --- |']
    names=['default','split_1','split_7','late_B','oversized_slow_prefix','slow_sink','aggregate_rate_control']+[f'path_p{p}_n{n}_s{s}_sequential_seed11_early1' for p in [1,2,3] for n,s in [(8,3),(32,8),(256,64)]]
    for name in names:
        for r in [r for r in paired if r['case']==name]:text.append(f'| {name} | {r["depth"]} | {r["A_rate"]:.6f} | {r["B_rate"]:.6f} | {r["H_rate"]:.6f} | {r["steady_H_vs_A"]} | {r["steady_H_vs_B"]} |')
    controls=[]
    for c in b.matrix():
        if c['early']!=0:continue
        on_name=c['name'].replace('_early0','_early1') if c['family']=='path' else c['name'].removesuffix('_gated')
        for depth in [1,2]:
            for mode in b.old.MODES:
                on,off=lookup[on_name,depth,mode],lookup[c['name'],depth,mode]
                assert on['config']==off['config'] and on['input_sha256']==off['input_sha256']
                a,bb=on['metrics'],off['metrics']
                controls.append(dict(case=on_name,profile=c['profile'],family=c['family'],depth=depth,mode=mode,
                    steady_early_vs_gated=b.old.outcome(a['steady']['cycles'],bb['steady']['cycles']),
                    early_cycles=a['steady']['cycles'],gated_cycles=bb['steady']['cycles'],
                    early_first_mean=a['latency']['command_first']['mean'],gated_first_mean=bb['latency']['command_first']['mean']))
    csvwrite('double-buffer-early-controls.csv',controls)
    text+=['','## Early-delivery controls','', '| Profile | Depth | Paired mode/configurations | Early on faster / tie / slower |', '| --- | ---: | ---: | --- |']
    for profile in range(4):
        for depth in [1,2]:
            selected=[r for r in controls if r['profile']==profile and r['depth']==depth]
            text.append(f'| P{profile} | {depth} | {len(selected)} | {wtl(selected,"steady_early_vs_gated")} |')
    text+=['','Each pair has identical memory settings, input files and capacity. Counts combine separately labeled modes/configurations only to describe these controls; consult the CSV for each baseline and split. Phase-dependent changes in admission can make early-on slower in a finite window.','']
    # Variability across the externally scheduled traces; keep profiles/settings separate.
    groups=collections.defaultdict(list)
    for r in runs:
        c=r['case']
        if c['family']=='path':groups[(c['profile'],c['N'],c['S'],c['early'],c['workload'],c['group'],r['depth'],r['mode'])].append(r)
    variability=[]
    for key,rr in groups.items():
        row=dict(zip(['profile','N','S','early','workload','group','depth','mode'],key));row['traces']=len(rr)
        for field,get in [('rate',lambda r:r['metrics']['steady']['words_per_cycle']),('first_mean',lambda r:r['metrics']['latency']['command_first']['mean']),('complete_p99',lambda r:r['metrics']['latency']['command_complete']['p99'])]:
            values=[get(r) for r in rr];row[field+'_min']=min(values);row[field+'_max']=max(values)
        variability.append(row)
    csvwrite('double-buffer-trace-ranges.csv',variability)
    flips=[]
    paired_lookup={(r['case'],r['depth']):r for r in paired}
    for c in b.matrix():
        if c['family']=='path' and c['group']=='sensitivity':
            for d in [1,2]:
                short=paired_lookup[c['name'].removesuffix('_long'),d];long=paired_lookup[c['name'],d]
                for label in 'AB':
                    field='steady_H_vs_'+label
                    if short[field]!=long[field]:flips.append(dict(case=c['name'],depth=d,baseline=label,short=short[field],long=long[field],short_H=short['H_cycles'],short_baseline=short[label+'_cycles'],long_H=long['H_cycles'],long_baseline=long[label+'_cycles']))
    text+=['','## Window sensitivity','',f'{len(flips)} hybrid-versus-baseline classifications change between the paired standard and doubled windows (both depths counted). Treat these as phase/window-sensitive comparisons.','']
    for r in flips:text.append(f'- {r["case"]}, depth {r["depth"]}, vs {r["baseline"]}: {r["short"]} → {r["long"]}.')
    (ROOT/'results/double-buffer-tables.md').write_text('\n'.join(text)+'\n')
    audit=dict(passed=True,runs=len(runs),matched_sets=len(b.matrix()),depth_one_historical_matches=1308,output_words=sum((r['case']['warmup']+r['case']['measured'])*r['case']['N'] for r in runs),window_flips=flips,source_sha256=report['source_sha256'])
    (b.OUT/'audit.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit|{'source_sha256':'verified'},indent=2))
if __name__=='__main__':main()
