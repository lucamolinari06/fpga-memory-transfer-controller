#!/usr/bin/env python3
"""Stage 4 native RTL experiments; historical sources and evidence are read-only."""
import argparse,csv,hashlib,json,platform,shutil,subprocess,tempfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import run_single_buffer as old
import importlib.util
_spec=importlib.util.spec_from_file_location('timing_benchmark_runner',Path(__file__).with_name('run_memory_timing.py'))
timing=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(timing)
from timing_inputs import bound,workload,write_calendar
ROOT=old.ROOT
OUT=ROOT/'results/raw/double_buffer'
SOURCES=timing.SOURCES[:-1]+['sim/models/behavioral_memory.sv','rtl/buffered_transfer_controller.sv','sim/tb/buffered_benchmark_tb.sv']
COUNTERS=old.COUNTERS+timing.EXTRA+['commands','grant_count']

def matrix():
    return [dict(c,profile=0,seed=None,workload='sequential',family='p0') for c in old.matrix()]+timing.matrix()

def rows(path):
    with path.open() as f:return [{k:int(v) for k,v in r.items()} for r in csv.DictReader(f)]

def summarize(path,c,mode,depth,cfg):
    rr=rows(path);n,w,m=c['N'],c['warmup'],c['measured'];bases=workload(n,c['workload'])
    assert len(rr)==w+m and rr[0]['command']==0
    lengths=[n,0] if mode==0 else [0,n] if mode==1 else [c['S'],n-c['S']]
    prev=None
    for j,r in enumerate(rr):
        assert (r['block'],r['base'],r['useful'])==(j,bases[j],(j+1)*n)
        assert r['useful']+r['unavailable']+r['intentional']==r['last']+1
        assert r['intentional']==r['last']+1-old.ready_before(r['last']+1,cfg)
        assert 0<=r['held']<=r['intentional']
        assert r['commands']-(j+1)==r['occupancy'] and 0<=r['occupancy']<depth
        assert r['a_beats']+r['b_beats']-r['useful']==r['backlog'] and 0<=r['backlog']<=depth*n
        assert 0<=r['steady_backlog_max']<=r['backlog_max']<=depth*n
        assert r['occupancy_max']<=depth
        if c['profile']:assert 0<=r['grant_count']-r['a_beats']-r['b_beats']<=2
        if prev:assert all(r[k]>=prev[k] for k in COUNTERS)
        for iface,length in zip('ab',lengths):
            q,f,d,v=[r[f'{k}_{iface}'] for k in ['request','response_first','response_last','valid_first']]
            assert r[f'{iface}_offered']==r[f'{iface}_beats'] and r[f'{iface}_blocked']==0
            if length:
                assert q>r['command'] and q%cfg[f'{iface}_accept_period']<cfg[f'{iface}_accept_cycles']
                assert f==v and f-q>=cfg[f'{iface}_latency']
                assert d-f>=(length-1)*cfg[f'{iface}_interval']
                if not c['profile']:
                    assert f-q==cfg[f'{iface}_latency']
                    assert d-f==(length-1)*cfg[f'{iface}_interval']+((length-1)//cfg[f'{iface}_burst'])*cfg[f'{iface}_gap']
                if prev:assert q>=prev[f'response_last_{iface}']+1+cfg[f'{iface}_cooldown']
            else:assert q==f==d==v==-1
        if prev:assert r['first']>=prev['last']+2
        assert r['last']-r['first']>=n-1
        if not c['early']:assert r['first']>=max(r['response_last_a'],r['response_last_b'])+2 and r['early_words']==0
        prev=r
    end,cut=rr[-1],rr[w-1]
    assert end['occupancy']==end['backlog']==0
    if c['profile']:assert end['grant_count']==end['useful']
    def window(prev):
        cycles=end['last']-(prev['last'] if prev else -1)
        counts={k:end[k]-(prev[k] if prev else 0) for k in COUNTERS}
        assert counts['useful']+counts['unavailable']+counts['intentional']==cycles
        assert counts['a_beats']+counts['b_beats']-counts['useful']==end['backlog']-(prev['backlog'] if prev else 0)
        completed=m if prev else w+m
        assert counts['commands']-completed==end['occupancy']-(prev['occupancy'] if prev else 0)
        if c['profile']:
            start_h=prev['grant_count']-prev['a_beats']-prev['b_beats'] if prev else 0
            assert counts['grant_count']-counts['a_beats']-counts['b_beats']==-start_h
            if c['profile']==3:assert counts['grant_count']<=cycles-counts['shared_reserved']
        return dict(cycles=cycles,words_per_cycle=counts['useful']/cycles,**counts,
                    slot_average=counts['slot_sum']/cycles,backlog_average=counts['backlog_sum']/cycles,
                    grant_rate=counts['grant_count']/cycles if c['profile'] else None,
                    backlog_start=prev['backlog'] if prev else 0,occupancy_start=prev['occupancy'] if prev else 0)
    latency={}
    for origin in ['command','request']:
        for label,key in [('first','first'),('complete','last')]:
            latency[origin+'_'+label]=timing.stats([r[key]-(r['command'] if origin=='command' else min(r['request_'+i] for i in 'ab' if r['request_'+i]>=0)) for r in rr[w:]])
    for i,length in zip('ab',lengths):
        if length:
            for k in ['valid_first','response_first','response_last']:
                latency[f'{i}_request_{k}']=timing.stats([r[k+'_'+i]-r['request_'+i] for r in rr[w:]])
    rates=[min(32,w+m-start)*n/(rr[min(start+32,w+m)-1]['last']-rr[start-1]['last']) for start in range(w,w+m,32)]
    return dict(whole_intervals=end['last'],startup_first=rr[0]['first'],whole=window(None),steady=window(cut),latency=latency,window32_rates=rates,window32_stats=timing.stats(rates),occupancy_max=end['occupancy_max'],backlog_max=end['backlog_max'])

class Builds:
    def __init__(self,root):
        self.root=root;root.mkdir(parents=True,exist_ok=True);self.hashes=old.hashes(SOURCES)
        digest=hashlib.sha256(json.dumps(self.hashes,sort_keys=True).encode()).hexdigest()[:16]
        self.work=Path(tempfile.gettempdir())/f'fpga-buffered-{digest}';self.work.mkdir(exist_ok=True)
        for p in SOURCES:shutil.copy2(ROOT/p,self.work/Path(p).name)
        self.fixture=self.work/'dataset.hex';old.dataset(self.fixture);self.cache={}
    def build(self,key):
        n,s,mode,early,depth,profiled=key;tag='_'.join(map(str,key));exe=self.work/f'obj_{tag}/benchmark'
        if not exe.exists():
            cmd=['verilator','--binary','--timing','--assert','--trace','-Wall','--top-module','buffered_benchmark_tb','--Mdir',f'obj_{tag}','-o','benchmark','-j','2']
            cmd += [f'-G{k}={v}' for k,v in zip(['BLOCK_WORDS','SPLIT_WORDS','MODE','EARLY_DELIVERY','BUFFER_COUNT','PROFILED'],key)]
            cmd += [Path(p).name for p in SOURCES]
            assert old.run(cmd,self.work,self.root/f'build_{tag}.log',180)==0,(self.root/f'build_{tag}.log').read_text()
            print('Built',tag,flush=True)
        return key,exe
    def ensure(self,c):
        keys=[(c['N'],c['S'],m,c['early'],d,int(c['profile']>0)) for d in [1,2] for m in range(3)]
        with ThreadPoolExecutor(max_workers=2) as pool:self.cache.update(pool.map(self.build,[k for k in keys if k not in self.cache]))
    def execute(self,c,mode,depth,calendar,bases,directory,extra=None):
        directory.mkdir(parents=True,exist_ok=True);cfg=dict(c['args'])
        if c['group']=='rate_control' and mode==2:cfg.update(a_interval=2,b_interval=2)
        key=(c['N'],c['S'],mode,c['early'],depth,int(c['profile']>0))
        if key not in self.cache:self.cache.update([self.build(key)])
        cmd=[str(self.cache[key]),f'+dataset={self.fixture}',f'+records={directory/"blocks.csv"}',f'+workload={bases}',f'+profile={c["profile"]}',f'+blocks={c["warmup"]+c["measured"]}',f'+warmup={c["warmup"]}']
        if calendar:cmd.append(f'+calendar={calendar}')
        cmd += [f'+{k}={v}' for k,v in dict(cfg,**(extra or {})).items()]
        code=old.run(cmd,directory,directory/'run.log',120)
        if code or 'PASS benchmark' not in (directory/'run.log').read_text():
            old.run(cmd+['+trace'],directory,directory/'trace-rerun.log',120)
            raise AssertionError((directory,(directory/'run.log').read_text()))
        return cfg,cmd

def reference_check(c,mode,path):
    refroot=old.OUT if c['profile']==0 else timing.OUT
    report=json.loads((refroot/'summary.json').read_text())
    match=[r for r in report['runs'] if r['case']['name']==c['name'] and r['mode']==old.MODES[mode]]
    assert len(match)==1
    ref=rows(ROOT/match[0]['records']);actual=rows(path)
    assert len(ref)==len(actual)
    for a,b in zip(actual,ref):assert all(a[k]==v for k,v in b.items()),(c['name'],mode,b['block'],[(k,a[k],v) for k,v in b.items() if a[k]!=v])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case');args=parser.parse_args()
    old.validate_prerequisites()
    for path in ['build/stage4/summary.json','build/stage4_extra/summary.json','build/stage4_parameters/summary.json','build/stage4_accounting/summary.json','build/memory_timing/summary.json','build/memory_timing_integration/summary.json']:
        gate=json.loads((ROOT/path).read_text());assert gate['passed'] and gate['source_sha256']==old.hashes(gate['source_sha256'])
    cases=matrix();assert len(cases)==436
    if args.case:cases=[c for c in cases if args.case in c['name']]
    build=Builds(OUT/'build_logs');inputs=OUT/'inputs';inputs.mkdir(exist_ok=True)
    manifest=old.hashes(SOURCES+['benchmarks/run_double_buffer.py','benchmarks/run_single_buffer.py','benchmarks/run_memory_timing.py','benchmarks/timing_inputs.py','tests/run_baseline.py'])
    descriptors={}
    for c in cases:
        bases=inputs/f'{c["workload"]}_n{c["N"]}.hex'
        if not bases.exists():bases.write_text(''.join(f'{b:08x}\n' for b in workload(c['N'],c['workload'])))
        calendar=None
        if c['profile']:
            calendar=timing.OUT/'inputs'/f'seed{c["seed"]}_length{bound(c,c["seed"])}.txt';assert calendar.exists()
        descriptors[c['name']]=(calendar,bases)
    report=dict(passed=False,scope='selected' if args.case else 'full',source_sha256=manifest,platform=platform.platform(),verilator=subprocess.check_output(['verilator','--version'],text=True).strip(),compiler=subprocess.check_output(['clang++','--version'],text=True).strip(),fixture_sha256=hashlib.sha256(build.fixture.read_bytes()).hexdigest(),matrix_sha256=hashlib.sha256(json.dumps(cases,sort_keys=True).encode()).hexdigest(),runs=[])
    for c in cases:
        build.ensure(c);calendar,bases=descriptors[c['name']]
        ih={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [calendar,bases] if p}
        ih['dataset']=report['fixture_sha256']
        for depth in [1,2]:
            for mode in range(3):
                directory=OUT/'runs'/f'{c["name"]}_d{depth}_m{mode}';result=directory/'result.json'
                entry=json.loads(result.read_text()) if result.exists() else {}
                if not(entry.get('passed') and entry.get('source_sha256')==manifest and entry.get('input_sha256')==ih):
                    cfg,cmd=build.execute(c,mode,depth,calendar,bases,directory)
                    metrics=summarize(directory/'blocks.csv',c,mode,depth,cfg)
                    if depth==1:reference_check(c,mode,directory/'blocks.csv')
                    entry=dict(case=c,mode=old.MODES[mode],depth=depth,passed=True,config=cfg,metrics=metrics,source_sha256=manifest,input_sha256=ih,command=cmd,records=str((directory/'blocks.csv').relative_to(ROOT)),records_sha256=hashlib.sha256((directory/'blocks.csv').read_bytes()).hexdigest())
                    result.write_text(json.dumps(entry,indent=2)+'\n')
                report['runs'].append(entry)
        print('PASS six matched runs',c['name'],flush=True)
    report['passed']=True;(OUT/('selected-summary.json' if args.case else 'summary.json')).write_text(json.dumps(report,indent=2)+'\n')
    print('PASS',len(report['runs']),'RTL benchmark runs',flush=True)
if __name__=='__main__':main()
