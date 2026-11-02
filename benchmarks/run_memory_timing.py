#!/usr/bin/env python3
"""Native RTL orchestration for the approved timing extension; preserves P0 evidence."""
import argparse, csv, hashlib, json, math, platform, shutil, statistics, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import run_single_buffer as old
from timing_inputs import SEEDS, bound, write_calendar, workload
ROOT=old.ROOT
OUT=ROOT/'results/raw/memory_timing'
SOURCES=['rtl/sync_bank.sv','rtl/single_memory_controller.sv','rtl/hybrid_controller.sv',
         'sim/models/profiled_memory_pair.sv','sim/models/timing_calendar.sv','sim/models/stream_sink.sv',
         'sim/tb/service_monitor.sv','sim/tb/address_scoreboard.sv','sim/tb/timing_benchmark_tb.sv']
EXTRA=['row_hits','row_closed','row_conflicts','a_grants','b_grants','pause_episodes','reserved_a','reserved_b','maintenance','shared_reserved']

def matrix():
    cases=[]
    for p in (1,2,3):
        for c in old.matrix():
            cases.append(dict(c,profile=p,seed=11,workload='sequential',family='legacy',legacy_name=c['name'],
                              name=f'legacy_p{p}_{c["name"]}'))
    def add(n,s,p,seed,early,kind='sequential',slow=False,long=False):
        name=f'path_p{p}_n{n}_s{s}_{kind}_seed{seed}_early{early}'+('_slow' if slow else '')+('_long' if long else '')
        cfg=dict(old.DEFAULTS,a_interval=1,b_latency=48,b_burst=16,b_gap=2,sink_period=16 if slow else 1)
        cases.append(dict(name=name,N=n,S=s,profile=p,seed=seed,early=early,workload=kind,family='path',
                          group='slow' if slow else 'sensitivity' if long else 'primary',
                          warmup=128 if long else 64,measured=2048 if long else 1024,args=cfg))
    splits=[(8,1),(8,3),(8,7),(32,8),(32,24),(256,64)]
    for p in (1,2,3):
        for n,s in splits:
            for early in (1,0):
                for seed in SEEDS: add(n,s,p,seed,early)
                add(n,s,p,11,early,slow=True)
        for n,s in [(8,3),(32,8)]:
            for kind in ('permuted','conflict'):
                for early in (1,0):
                    for seed in SEEDS: add(n,s,p,seed,early,kind)
        for early in (1,0):
            for seed in SEEDS: add(8,3,p,seed,early,'expanded')
    for p in (2,3):
        for kind in ('sequential','conflict'):
            for early in (1,0):
                for seed in SEEDS:add(8,3,p,seed,early,kind,long=True)
    assert len(cases)==410 and len({c['name'] for c in cases})==410
    return cases

def stats(values):
    v=sorted(values)
    return dict(min=v[0],median=statistics.median(v),mean=statistics.mean(v),
                p95=v[math.ceil(.95*len(v))-1],p99=v[math.ceil(.99*len(v))-1],max=v[-1])

def summarize(path,c,mode,cfg,bases):
    with path.open() as stream:
        rows=[{k:int(v) for k,v in r.items()} for r in csv.DictReader(stream)]
    n,s,w,m=c['N'],c['S'],c['warmup'],c['measured']
    assert len(rows)==w+m and rows[0]['command']==0
    lengths=[n,0] if mode==0 else [0,n] if mode==1 else [s,n-s]
    previous=None
    for j,r in enumerate(rows):
        assert (r['block'],r['base'],r['useful'])==(j,bases[j],(j+1)*n)
        assert r['useful']+r['unavailable']+r['intentional']==r['last']+1
        assert r['intentional']==r['last']+1-old.ready_before(r['last']+1,cfg)
        assert r['held']<=r['intentional'] and 0<=r['steady_backlog_max']<=r['backlog_max']<=n
        assert r['slot_sum']==r['last']+1-(j+1)
        if previous:
            assert r['command']==previous['last']+1
            assert all(r[k]>=previous[k] for k in old.COUNTERS+EXTRA)
        for iface,length in zip('ab',lengths):
            req,f,d,v=[r[f'{k}_{iface}'] for k in ['request','response_first','response_last','valid_first']]
            assert r[f'{iface}_requests']==(j+1)*(length>0)
            assert r[f'{iface}_beats']==r[f'{iface}_grants']==(j+1)*length
            assert r[f'{iface}_offered']==r[f'{iface}_beats'] and r[f'{iface}_blocked']==0
            if length:
                assert req>r['command'] and req%cfg[f'{iface}_accept_period']<cfg[f'{iface}_accept_cycles']
                assert f==v and f-req>=cfg[f'{iface}_latency']
                assert d-f>=(length-1)*cfg[f'{iface}_interval']
                assert r[f'{iface}_busy']-(previous[f'{iface}_busy'] if previous else 0)==d-req
                if previous:assert req>=previous[f'response_last_{iface}']+1+cfg[f'{iface}_cooldown']
            else: assert req==f==d==v==-1
        assert r['last']-r['first']>=n-1
        if not c['early']:
            assert r['first']>=max(r['response_last_a'],r['response_last_b'])+2 and r['early_words']==0
        previous=r
    end,cut=rows[-1],rows[w-1]
    def window(start,prev):
        cycles=end['last']-start
        counts={k:end[k]-(prev[k] if prev else 0) for k in old.COUNTERS+EXTRA}
        assert counts['useful']+counts['unavailable']+counts['intentional']==cycles
        if c['profile']==3: assert counts['a_grants']+counts['b_grants']<=cycles-counts['shared_reserved']
        return dict(cycles=cycles,words_per_cycle=counts['useful']/cycles,**counts,
                    slot_average=counts['slot_sum']/cycles,backlog_average=counts['backlog_sum']/cycles,
                    a_service_rate=counts['a_grants']/cycles,b_service_rate=counts['b_grants']/cycles,
                    shared_utilization=(counts['a_grants']+counts['b_grants'])/cycles if c['profile']==3 else None)
    measured=rows[w:];latency={}
    for name,key in [('command_first','first'),('command_complete','last')]:
        latency[name]=stats([r[key]-r['command'] for r in measured])
    for name,key in [('request_first','first'),('request_complete','last')]:
        latency[name]=stats([r[key]-min(r[f'request_{i}'] for i in 'ab' if r[f'request_{i}']>=0) for r in measured])
    latency['request_skew']=stats([abs(r['request_a']-r['request_b']) if min(r['request_a'],r['request_b'])>=0 else 0 for r in measured])
    for i,length in zip('ab',lengths):
        if length:
            for name in ['valid_first','response_first','response_last']:
                latency[f'{i}_request_{name}']=stats([r[f'{name}_{i}']-r[f'request_{i}'] for r in measured])
    rates=[]
    for start in range(w,w+m,32):
        count=min(32,w+m-start)
        rates.append(count*n/(rows[start+count-1]['last']-rows[start-1]['last']))
    return dict(whole_intervals=end['last'],startup_first=rows[0]['first'],whole=window(-1,None),
                steady=window(cut['last'],cut),latency=latency,window32_rates=rates,window32_stats=stats(rates))

class Builds:
    def __init__(self,root):
        self.root=root;self.root.mkdir(parents=True,exist_ok=True)
        self.hashes=old.hashes(SOURCES)
        digest=hashlib.sha256(json.dumps(self.hashes,sort_keys=True).encode()).hexdigest()[:16]
        # Stable whitespace-free, source-specific native cache; provenance is checked before reuse.
        self.work=Path(tempfile.gettempdir())/f'fpga-timing-{digest}'
        self.work.mkdir(exist_ok=True)
        for p in SOURCES:shutil.copy2(ROOT/p,self.work/Path(p).name)
        self.fixture=self.work/'dataset.hex';old.dataset(self.fixture)
        self.cache={}
    def build(self,key):
        n,s,mode,early=key;tag=f'{n}_{s}_{mode}_{early}';exe=self.work/f'obj_{tag}/benchmark'
        if not exe.exists():
            cmd=['verilator','--binary','--timing','--assert','--trace','-Wall','--top-module','timing_benchmark_tb',
                 '--Mdir',f'obj_{tag}','-o','benchmark','-j','2',f'-GBLOCK_WORDS={n}',f'-GSPLIT_WORDS={s}',
                 f'-GMODE={mode}',f'-GEARLY_DELIVERY={early}']+[Path(p).name for p in SOURCES]
            assert old.run(cmd,self.work,self.root/f'build_{tag}.log',180)==0,(self.root/f'build_{tag}.log').read_text()
            print('Built',tag,flush=True)
        return key,exe
    def ensure(self,c):
        keys=[(c['N'],c['S'],mode,c['early']) for mode in range(3)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.cache.update(pool.map(self.build,[k for k in keys if k not in self.cache]))
    def execute(self,c,mode,calendar,bases,directory,extra=None):
        directory.mkdir(exist_ok=True,parents=True)
        cfg=dict(c['args'])
        if c['group']=='rate_control' and mode==2:cfg.update(a_interval=2,b_interval=2)
        key=(c['N'],c['S'],mode,c['early'])
        if key not in self.cache:self.cache.update([self.build(key)])
        cmd=[str(self.cache[key]),f'+dataset={self.fixture}',f'+records={directory/"blocks.csv"}',
             f'+calendar={calendar}',f'+workload={bases}',f'+profile={c["profile"]}',
             f'+blocks={c["warmup"]+c["measured"]}',f'+warmup={c["warmup"]}']
        cmd += [f'+{k}={v}' for k,v in dict(cfg,**(extra or {})).items()]
        code=old.run(cmd,directory,directory/'run.log',120)
        if code!=0 or 'PASS benchmark' not in (directory/'run.log').read_text():
            old.run(cmd+['+trace'],directory,directory/'trace-rerun.log',120)
            raise AssertionError((directory,(directory/'run.log').read_text()))
        return cfg,cmd

def verify():
    root=ROOT/'build/memory_timing_integration';build=Builds(root)
    write_calendar(root/'table.txt',4096,schedule=[(1,0,0)]*3+[(4096,1,22)],jitter=False)
    (root/'zero.hex').write_text('00000000\n'*8192)
    c=dict(N=4,S=2,early=1,args=dict(old.DEFAULTS,a_interval=1,b_latency=2),group='verify',profile=3,warmup=1,measured=1)
    build.execute(c,2,root/'table.txt',root/'zero.hex',root/'table',dict(eventlog=root/'table/events.csv'))
    r=list(csv.reader((root/'table/events.csv').open()))
    outputs=[int(x[0])-20 for x in r if x[1]=='output' and int(x[0])>=20]
    assert outputs==[4,7,8,9],outputs
    checks=[dict(name='hand_table_output',passed=True,edges=outputs)]
    for mode in range(3):
        for early in (0,1):
            for seed in SEEDS:
                name=f'm{mode}_e{early}_seed{seed}';write_calendar(root/f'{seed}.txt',65536,seed)
                c.update(N=8,S=3,early=early,warmup=1,measured=3,
                         args=dict(old.DEFAULTS,a_interval=1,b_latency=48,sink_period=5,sink_cycles=2))
                build.execute(c,mode,root/f'{seed}.txt',root/'zero.hex',root/name)
                checks.append(dict(name=name,passed=True))
            # A word is held at controller output while scheduled sink blocks edges 0..99.
            c.update(args=dict(old.DEFAULTS,a_interval=1,b_latency=48,stall_start=0,stall_length=100))
            build.execute(c,mode,root/'11.txt',root/'zero.hex',root/f'reset_{mode}_{early}',dict(reset_at=80))
            checks.append(dict(name=f'reset_output_{mode}_{early}',passed=True))
    report=dict(passed=True,source_sha256=build.hashes,cases=checks)
    (root/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(f'PASS {len(checks)} integration outcomes',flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--verify-only',action='store_true');parser.add_argument('--case')
    args=parser.parse_args()
    if args.verify_only:verify();return
    old.validate_prerequisites()
    for p in ['build/memory_timing/summary.json','build/memory_timing_integration/summary.json']:
        report=json.loads((ROOT/p).read_text());assert report['passed']
        assert report['source_sha256']==old.hashes(report['source_sha256'])
    cases=matrix()
    if args.case:cases=[c for c in cases if args.case in c['name']]
    assert cases
    build=Builds(OUT/'build_logs');inputs=OUT/'inputs';inputs.mkdir(exist_ok=True)
    manifest=old.hashes(SOURCES+['benchmarks/run_memory_timing.py','benchmarks/timing_inputs.py'])
    report=dict(passed=False,scope='selected' if args.case else 'full',source_sha256=manifest,
                platform=platform.platform(),verilator=subprocess.check_output(['verilator','--version'],text=True).strip(),
                fixture_sha256=hashlib.sha256(build.fixture.read_bytes()).hexdigest(),runs=[],comparisons=[])
    # Generate every selected input before starting any selected DUT performance run.
    descriptors={}
    for c in cases:
        length=bound(c,c['seed']);calendar=inputs/f'seed{c["seed"]}_length{length}.txt'
        if not calendar.exists():write_calendar(calendar,length,c['seed'])
        bases=inputs/f'{c["workload"]}_n{c["N"]}.hex'
        if not bases.exists():bases.write_text(''.join(f'{b:08x}\n' for b in workload(c['N'],c['workload'])))
        descriptors[c['name']]=(calendar,bases)
    print('All external input files prepared before simulations;',len(cases),'triplets',flush=True)
    for c in cases:
        build.ensure(c);calendar,bases=descriptors[c['name']]
        ih={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [calendar,bases]}
        runs=[]
        for mode in range(3):
            directory=OUT/'runs'/f'{c["name"]}_m{mode}';result=directory/'result.json'
            entry=json.loads(result.read_text()) if result.exists() else {}
            if not (entry.get('passed') and entry.get('source_sha256')==manifest and entry.get('input_sha256')==ih):
                cfg,cmd=build.execute(c,mode,calendar,bases,directory)
                metrics=summarize(directory/'blocks.csv',c,mode,cfg,workload(c['N'],c['workload']))
                entry=dict(case=c,mode=old.MODES[mode],passed=True,config=cfg,metrics=metrics,
                           source_sha256=manifest,input_sha256=ih,command=cmd,
                           records=str((directory/'blocks.csv').relative_to(ROOT)))
                result.write_text(json.dumps(entry,indent=2)+'\n')
            runs.append(entry);report['runs'].append(entry)
        a,b,h=[r['metrics'] for r in runs]
        if c['S'] in (0,c['N']): assert h==(b if c['S']==0 else a),'Endpoint equivalence'
        comparison=dict(case=c['name'],family=c['family'],group=c['group'],profile=c['profile'],seed=c['seed'],
                        N=c['N'],S=c['S'],early=c['early'],workload=c['workload'])
        for mode,metrics in zip('ABH',[a,b,h]):
            comparison[mode+'_whole']=metrics['whole_intervals'];comparison[mode+'_steady_cycles']=metrics['steady']['cycles']
            comparison[mode+'_rate']=metrics['steady']['words_per_cycle']
            comparison[mode+'_first_mean']=metrics['latency']['command_first']['mean']
            comparison[mode+'_complete_p99']=metrics['latency']['command_complete']['p99']
        for label,other in [('A',a),('B',b)]:
            comparison['whole_H_vs_'+label]=old.outcome(h['whole_intervals'],other['whole_intervals'])
            comparison['steady_H_vs_'+label]=old.outcome(h['steady']['cycles'],other['steady']['cycles'])
        report['comparisons'].append(comparison)
        print(f'PASS {c["name"]}: rates A/B/H={a["steady"]["words_per_cycle"]:.6f}/{b["steady"]["words_per_cycle"]:.6f}/{h["steady"]["words_per_cycle"]:.6f}',flush=True)
    report['passed']=True
    target=OUT/('selected-summary.json' if args.case else 'summary.json')
    target.write_text(json.dumps(report,indent=2)+'\n')
    with target.with_suffix('.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(report['comparisons'][0]));writer.writeheader();writer.writerows(report['comparisons'])
    print('PASS',len(report['runs']),'new-profile RTL runs',flush=True)
if __name__=='__main__':main()
