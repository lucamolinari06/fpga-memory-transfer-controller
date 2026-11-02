#!/usr/bin/env python3
"""Actual RTL model checks, independent fixed expectations and named negative faults."""
import csv, hashlib, json, shutil, sys, tempfile
from pathlib import Path
from run_baseline import ROOT,dataset,run
sys.path.insert(0,str(ROOT/'benchmarks'))
from timing_inputs import write_calendar, events, active
OUT=ROOT/'build/memory_timing'
SOURCES=['sim/models/timing_calendar.sv','sim/models/profiled_memory_pair.sv',
         'sim/tb/service_monitor.sv','sim/tb/profiled_memory_tb.sv']

def rows(path):
    with path.open() as stream:
        return [{k:int(v) for k,v in r.items()} for r in csv.DictReader(stream)]

def main():
    OUT.mkdir(exist_ok=True,parents=True)
    work=Path(tempfile.mkdtemp(prefix='fpga-memory-tests-'))
    for p in SOURCES: shutil.copy2(ROOT/p,work/Path(p).name)
    dataset(work/'dataset.hex')
    cmd=['verilator','--binary','--timing','--assert','--trace','-Wall','--top-module','profiled_memory_tb',
         '--Mdir','obj','-o','test','-j','2']+[Path(p).name for p in SOURCES]
    assert run(cmd,work,OUT/'build.log',180)==0, (OUT/'build.log').read_text()
    quiet=[(1,0,0)]*4
    write_calendar(OUT/'quiet.txt',4096,schedule=quiet,jitter=False)
    # Row prime request accepts edge 1, response 15, drain ends 18; paired request edge 19.
    # Transport reservation normalized edge 2 => absolute edge 21.
    write_calendar(OUT/'table.txt',4096,schedule=quiet[:3]+[(4096,1,21)],jitter=False)
    write_calendar(OUT/'pauses.txt',4096,schedule=[(3,2,0),(64,16,20),(128,32,25),(64,8,3)],jitter=False)
    write_calendar(OUT/'short.txt',2,schedule=quiet,jitter=False)
    (OUT/'bad.txt').write_text('4096\n1 0 0\n')
    (OUT/'trailing.txt').write_text((OUT/'quiet.txt').read_text()+'junk\n')
    tests=[('rows',0,'quiet',1,None,0),('rows_shared',0,'quiet',3,None,0),('table',1,'table',3,None,0),('holds',2,'pauses',3,None,0),
           ('minimum',8,'quiet',3,None,0)]
    tests += [(f'reset_{i}',i,'pauses',3,None,0) for i in [3,4,5,6,7,9]]
    tests += [("setup_pause",10,"pauses",3,None,0)]
    tests += [(f'trace_{seed}',0,f'seed{seed}',3,None,0) for seed in [11,29,47,83]]
    for seed in [11,29,47,83]: write_calendar(OUT/f'seed{seed}.txt',4096,seed)
    tests += [('missing',0,'missing',1,'TRACE_OPEN',0),('malformed',0,'bad',1,'TRACE_FORMAT',0),
              ('exhausted',0,'short',1,'TRACE_EXHAUSTED',0),('trailing',0,'trailing',1,'TRACE_FORMAT_EXTRA',0)]
    tests += [(name,6 if f==7 else 2,'pauses',3,error,f) for f,name,error in [
        (1,'withdraw','MON_CONSERVATION'),(2,'mutate_held','MON_RESPONSE_STABILITY'),
        (3,'duplicate','MON_DATA'),(4,'wrong_last','MON_LAST'),(5,'overcapacity','MON_SHARED_CAPACITY'),
        (6,'reserved_grant','MON_RESERVED_GRANT'),(7,'stale','MON_CONSERVATION'),(8,'drop','MON_CONSERVATION')]]
    report=dict(passed=False,source_sha256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in SOURCES},cases=[])
    try:
        for name,scenario,calendar,profile,error,fault in tests:
            directory=OUT/name;directory.mkdir(exist_ok=True)
            cmd=[str(work/'obj/test'),f'+dataset={work/"dataset.hex"}',f'+calendar={OUT/(calendar+".txt")}',
                 f'+events={directory/"events.csv"}',f'+scenario={scenario}',f'+profile={profile}',f'+fault={fault}', '+trace']
            code=run(cmd,directory,directory/'run.log',30);log=(directory/'run.log').read_text()
            ok=(code==0 and 'PASS profiled memory' in log) if not error else code not in (0,124) and error in log
            report['cases'].append(dict(name=name,passed=ok,exit_code=code,expected_failure=error,command=cmd))
            assert ok,(name,log)
            print('PASS',name,flush=True)
        r=rows(OUT/'rows/events.csv')
        requests=[x['cycle'] for x in r if x['request']&2]
        firsts=[]
        for i,start in enumerate(requests):
            end=requests[i+1] if i+1<len(requests) else 9999
            firsts.append(next(x['cycle']-start for x in r if start<=x['cycle']<end and x['valid']&2))
        assert firsts==[14,2,26,14,26,2,14],firsts
        assert (r[-1]['hits'],r[-1]['closed'],r[-1]['conflicts'])==(5,3,3),r[-1]
        assert (OUT/"rows/events.csv").read_bytes()==(OUT/"rows_shared/events.csv").read_bytes()
        r=rows(OUT/'table/events.csv');start=next(x['cycle'] for x in r if x['request']==3)
        grants=[(x['cycle']-start,x['grant']) for x in r if x['cycle']>=start and x['grant']]
        responses=[(x['cycle']-start,x['valid']&x['ready']) for x in r if x['cycle']>=start and x['valid']&x['ready']]
        assert grants==[(1,1),(3,2),(4,1),(5,2)],(start,grants)
        assert responses==[(2,1),(4,2),(5,1),(6,2)],responses
        r=rows(OUT/'minimum/events.csv');start=next(x['cycle'] for x in r if x['request']==1)
        assert [x['cycle']-start for x in r if x['grant']==1]==list(range(5))
        r=rows(OUT/'setup_pause/events.csv')
        req=next(x['cycle'] for x in r if x['request']==2)
        first=next(x['cycle'] for x in r if x['valid']&2)
        assert (req,first)==(20,76),(req,first)
        # Holds cross maintenance and reserved service without response withdrawal.
        r=rows(OUT/'holds/events.csv')
        assert any(x['valid']==3 and x['ready']==0 and x['reserved']&4 for x in r)
        assert any(x['valid']&2 and x['last']&2 and x['ready']==0 for x in r)
        for seed in [11,29,47,83]:
            for event in rows(OUT/f'trace_{seed}/events.csv'):
                expected=sum(int(active(event['cycle'],schedule))<<i for i,schedule in enumerate(events(seed)))
                assert event['reserved']==expected
        # Replay is byte-identical, not merely same seed text.
        write_calendar(work/'repeat.txt',4096,11)
        assert (work/'repeat.txt').read_bytes()==(OUT/'seed11.txt').read_bytes()
        report['fixed_checks']={'row_first_latencies':firsts,'table_grants':grants,'table_responses':responses}
        report['passed']=True
    finally:
        (OUT/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        print('Build retained:',work,flush=True)
    print(f'PASS {len(tests)} model outcomes and fixed-table checks',flush=True)
if __name__=='__main__':main()
