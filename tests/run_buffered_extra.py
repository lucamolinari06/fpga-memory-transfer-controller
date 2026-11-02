#!/usr/bin/env python3
"""Structural witnesses and deliberate checker/RTL faults, separate from performance."""
import csv,hashlib,json,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'benchmarks'))
import run_double_buffer as bench
from timing_inputs import workload,write_calendar

def main():
    root=ROOT/'build/stage4_extra';build=bench.Builds(root);checks=[]
    bases=root/'bases.hex';bases.write_text(''.join(f'{b:08x}\n' for b in workload(8,'sequential')))
    calendar=root/'calendar.txt';write_calendar(calendar,65536,11)
    c=dict(name='extra',N=8,S=3,early=1,profile=0,workload='sequential',warmup=1,measured=7,group='verify',args=dict(bench.old.DEFAULTS))
    def run(name,args=None,extra=None,profile=0,expected=(),cal=None):
        case=dict(c,profile=profile,args=dict(c['args'],**(args or {})))
        directory=root/name
        cfg,cmd=build.execute(case,2,2,cal or calendar,bases,directory,extra)
        log=(directory/'run.log').read_text()
        for token in expected:assert token in log,(name,token,log)
        if not(extra and extra.get('reset_at')):bench.summarize(directory/'blocks.csv',case,2,2,cfg)
        checks.append(dict(name=name,passed=True,witnesses=list(expected),command=cmd))
        return cmd
    cmd=run('overlap_wrap',expected=['full=1','split_owner=1','overlap=1'])
    run('simultaneous',extra=dict(second_edge=16),expected=['simultaneous=1'])
    run('held_final',args=dict(stall_start=16,stall_length=50),expected=['held_last=1','full=1'])
    run('pinned_across_retirement',args=dict(a_accept_period=17),expected=['pending_retire=1','request_stall=1'])
    run('b_first',args=dict(a_latency=40,b_latency=2,a_interval=1),expected=['full=1'])
    run('reset_both_busy',args=dict(stall_start=0,stall_length=100),extra=dict(reset_at=3),expected=['RESET_WITNESS occupied=2 activeA=1 activeB=1'])
    run('reset_pending',args=dict(a_accept_period=17,b_accept_period=31,stall_start=0,stall_length=100),extra=dict(reset_at=4),expected=['pendingA=1 pendingB=1'])
    run('reset_tail_owners',args=dict(stall_start=0,stall_length=100),extra=dict(reset_at=14,eventlog=root/'reset_tail_owners/events.csv'),expected=['RESET_WITNESS occupied=2 activeA=1 activeB=1'])
    ee=list(csv.reader((root/'reset_tail_owners/events.csv').open()))
    assert any(r[1]=='request0' and r[2]=='264' and int(r[0])<14 for r in ee)
    assert any(r[1]=='request1' and r[2]=='267' and int(r[0])<14 for r in ee)
    run('reset_held_final',args=dict(stall_start=16,stall_length=100),extra=dict(reset_at=18),expected=['held=1 last=1'])
    maintenance=root/'maintenance.txt';write_calendar(maintenance,65536,schedule=[(1,0,0),(1,0,0),(2048,32,0),(1,0,0)],jitter=False)
    run('reset_maintenance',profile=2,cal=maintenance,args=dict(stall_start=0,stall_length=100),extra=dict(reset_at=10),expected=['maintenance=1'])
    # Runtime wrappers modify only inputs to the unchanged address-only scoreboard.
    for fault,name,diagnostic in [(1,'corrupt','DATA_MISMATCH'),(2,'last','OUTPUT_LAST_MISMATCH'),(3,'duplicate','DATA_MISMATCH'),(4,'drop','CHECKER_MISSING_OUTPUT')]:
        directory=root/('fault_'+name);directory.mkdir(exist_ok=True)
        command=[x if not x.startswith('+records=') else f'+records={directory/"blocks.csv"}' for x in cmd]+[f'+fault={fault}','+trace']
        code=bench.old.run(command,directory,directory/'run.log',120)
        log=(directory/'run.log').read_text();assert code not in (0,124) and diagnostic in log,(name,code,log)
        checks.append(dict(name='fault_'+name,passed=True,expected_failure=diagnostic,returncode=code,command=command))
    # Test-only source mutations are isolated from the implementation and all performance builds.
    mutations=[
        ('wrong_owner','owner[i]==32\'(s)','head==32\'(s)','BANK_WRITE_BOUNDS',{}),
        ('invalid_read','&& readable &&','&& 1\'b1 &&','INVALID_READ',{}),
        ('premature_free','assign retire = out_valid && out_ready && out_last;','assign retire = out_valid && out_last;','BENCH_REUSE',dict(stall_start=16,stall_length=50)),
        ('request_instability','req_base[i]=base[selected[i]]+','req_base[i]=base[selected[i]]+32\'(reads[head])+','A_REQUEST_STABILITY',dict(a_accept_period=17)),
        ('output_instability','assign out_data = bank_data[output_slot][output_bank];','assign out_data = bank_data[output_slot][output_bank]^32\'(received[0]);','OUTPUT_STABILITY',dict(stall_start=5,stall_length=50)),
        ('stale_reset','output_valid<=0;output_last<=0;output_bank<=0;output_slot<=0;','if (output_valid !== 1\'b1) output_valid<=0;output_last<=0;output_bank<=0;output_slot<=0;','OUTPUT_OWNERSHIP',dict(stall_start=0,stall_length=100,reset_at=18)),
    ]
    for name,source,replacement,diagnostic,extra in mutations:
        directory=root/('fault_'+name);directory.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='fpga-buffered-fault-') as temp:
            work=Path(temp)
            for p in bench.SOURCES:shutil.copy2(ROOT/p,work/Path(p).name)
            rtl=work/'buffered_transfer_controller.sv';original=rtl.read_text();assert original.count(source)==1
            rtl.write_text(original.replace(source,replacement));shutil.copy2(rtl,directory/'mutated.sv')
            command=['verilator','--binary','--timing','--assert','--trace','-Wall','--top-module','buffered_benchmark_tb','--Mdir','obj','-o','test','-j','2','-GMODE=2']+[Path(p).name for p in bench.SOURCES]
            assert bench.old.run(command,work,directory/'build.log',180)==0,(directory/'build.log').read_text()
            command=[str(work/'obj/test'),f'+dataset={build.fixture}',f'+workload={bases}',f'+records={directory/"blocks.csv"}','+blocks=8','+warmup=1','+profile=0','+trace']+[f'+{k}={v}' for k,v in extra.items()]
            code=bench.old.run(command,directory,directory/'run.log',120);log=(directory/'run.log').read_text()
            assert code not in (0,124) and diagnostic in log,(name,diagnostic,code,log)
            checks.append(dict(name='fault_'+name,passed=True,expected_failure=diagnostic,returncode=code,mutation_sha256=hashlib.sha256(rtl.read_bytes()).hexdigest()))
    # A dedicated observation-only harness proves shared reset actually interrupts B row setup.
    directory=root/'reset_row_setup';directory.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fpga-buffered-row-reset-') as temp:
        work=Path(temp)
        for p in bench.SOURCES:shutil.copy2(ROOT/p,work/Path(p).name)
        harness=work/'buffered_benchmark_tb.sv'
        harness.write_text(harness.read_text().replace('profiled_memory_pair memory_pair(.*);',"""profiled_memory_pair memory_pair(.*);
            always @(negedge clk) if (!rst && cycle==10 && base_shift==0) begin
                assert (memory_pair.setup_active) else $fatal(1,\"ROW_SETUP_NOT_WITNESSED\");
                $display(\"ROW_SETUP_WITNESS\");
            end"""))
        shutil.copy2(harness,directory/'observed_tb.sv')
        command=['verilator','--binary','--timing','--assert','--trace','-Wall','--top-module','buffered_benchmark_tb','--Mdir','obj','-o','test','-j','2','-GMODE=2','-GPROFILED=1']+[Path(p).name for p in bench.SOURCES]
        assert bench.old.run(command,work,directory/'build.log',180)==0,(directory/'build.log').read_text()
        command=[str(work/'obj/test'),f'+dataset={build.fixture}',f'+workload={bases}',f'+records={directory/"blocks.csv"}',f'+calendar={calendar}','+blocks=8','+warmup=1','+profile=1','+b_latency=2','+stall_start=0','+stall_length=100','+reset_at=11']
        code=bench.old.run(command,directory,directory/'run.log',120);log=(directory/'run.log').read_text()
        assert code==0 and 'ROW_SETUP_WITNESS' in log and 'PASS benchmark' in log,log
        checks.append(dict(name='reset_row_setup',passed=True,witnesses=['ROW_SETUP_WITNESS'],harness_sha256=hashlib.sha256(harness.read_bytes()).hexdigest()))
    report=dict(passed=True,source_sha256=bench.old.hashes(bench.SOURCES+['tests/run_buffered_extra.py']),cases=checks)
    (root/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print('PASS',len(checks),'extra Stage 4 outcomes',flush=True)
if __name__=='__main__':main()
