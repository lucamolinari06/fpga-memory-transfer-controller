#!/usr/bin/env python3
"""Directed Stage 4 correctness checks using the public-channel RTL harness."""
import csv,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'benchmarks'))
import run_double_buffer as bench
from timing_inputs import workload,write_calendar

def main():
    root=ROOT/'build/stage4';build=bench.Builds(root);checks=[]
    write_calendar(root/'calendar.txt',1048576,11)
    def run(name,n=8,s=3,mode=2,early=1,depth=2,profile=0,args=None,extra=None,blocks=6):
        c=dict(name=name,N=n,S=s,early=early,profile=profile,workload='sequential',warmup=1,measured=blocks-1,group='verify',args=dict(bench.old.DEFAULTS,**(args or {})))
        bases=root/f'n{n}.hex';bases.write_text(''.join(f'{b:08x}\n' for b in workload(n,'sequential')))
        directory=root/name
        cfg,cmd=build.execute(c,mode,depth,root/'calendar.txt',bases,directory,extra)
        if not(extra and extra.get('reset_at')):bench.summarize(directory/'blocks.csv',c,mode,depth,cfg)
        checks.append(dict(name=name,passed=True,command=cmd))
        return directory
    d=run('hand_table',blocks=2,extra=dict(eventlog=root/'hand_table/events.csv'))
    events=list(csv.reader((d/'events.csv').open()))
    assert [int(r[0]) for r in events if r[1]=='output']==[5,8,11,12,13,14,15,16,18,19,20,21,22,23,24,25]
    assert [int(r[0]) for r in events if r[1]=='read']==[4,7,10,11,12,13,14,15,17,18,19,20,21,22,23,24]
    for n in [1,2,8,256]:
        for s in sorted(set([0,1,n-1,n])):
            for mode in range(3):
                for early in [0,1]:
                    for depth in [1,2]:run(f'n{n}_s{s}_m{mode}_e{early}_d{depth}',n,s,mode,early,depth,blocks=4,args=dict(sink_period=5,sink_cycles=2,a_accept_period=7,b_accept_period=11))
    for p in [0,1,2,3]:
        for mode in range(3):
            for early in [0,1]:
                run(f'profile{p}_m{mode}_e{early}',mode=mode,early=early,profile=p,args=dict(a_interval=1,b_latency=48,sink_period=7,sink_cycles=3),blocks=20)
                run(f'reset_p{p}_m{mode}_e{early}',mode=mode,early=early,profile=p,args=dict(a_interval=1,b_latency=48,stall_start=0,stall_length=100),extra=dict(reset_at=80))
    (root/'summary.json').write_text(json.dumps(dict(passed=True,source_sha256=bench.old.hashes(bench.SOURCES+['tests/run_buffered.py']),cases=checks),indent=2)+'\n')
    print('PASS',len(checks),'Stage 4 positive RTL cases',flush=True)
if __name__=='__main__':main()
