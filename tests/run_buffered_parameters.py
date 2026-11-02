#!/usr/bin/env python3
"""New depth/mode rejection in a minimal RTL harness, independently of benchmark guards."""
import json,re,shutil,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'benchmarks'))
import run_double_buffer as b
root=ROOT/'build/stage4_parameters';root.mkdir(exist_ok=True);checks=[]
source=(ROOT/'rtl/buffered_transfer_controller.sv').read_text()
ports=source.split(') (',1)[1].split(');',1)[0]
declarations=re.sub(r'\b(input|output) ', '',ports)
declarations='\n'.join(line.rstrip().rstrip(',')+';' for line in declarations.splitlines() if line.strip())
inputs=[]
for line in ports.splitlines():
    if 'input logic' in line:inputs.extend(re.sub(r'input logic(?: \[[^]]+\])?', '',line).strip().rstrip(',').replace(' ','').split(','))
assignments='\n'.join(f'assign {name}=0;' for name in inputs if name!='clk')
tb='''module parameter_tb #(parameter int unsigned BUFFER_COUNT=2, MODE=2);
    timeunit 1ns;timeprecision 1ps;
    // Outputs are intentionally unobserved: this test must fail at time zero.
    /* verilator lint_off UNUSEDSIGNAL */
'''+declarations+'''\n    /* verilator lint_on UNUSEDSIGNAL */
    initial clk=0;always #5 clk=~clk;
'''+assignments+'''
    buffered_transfer_controller #(.BUFFER_COUNT(BUFFER_COUNT),.MODE(MODE)) dut(.*);
    initial begin #20;$fatal(1,"PARAMETER_UNEXPECTEDLY_ACCEPTED");end
endmodule
'''
(root/'parameter_tb.sv').write_text(tb)
for depth,mode,diagnostic in [(0,2,'PARAM_BUFFER_COUNT'),(3,2,'PARAM_BUFFER_COUNT'),(2,3,'PARAM_MODE')]:
    directory=root/f'd{depth}_m{mode}';directory.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='fpga-parameter-') as temp:
        work=Path(temp)
        for p in ['rtl/sync_bank.sv','rtl/buffered_transfer_controller.sv']:shutil.copy2(ROOT/p,work/Path(p).name)
        (work/'parameter_tb.sv').write_text(tb)
        cmd=['verilator','--binary','--timing','--assert','-Wall','--top-module','parameter_tb','--Mdir','obj','-o','test','-j','2',f'-GBUFFER_COUNT={depth}',f'-GMODE={mode}','sync_bank.sv','buffered_transfer_controller.sv','parameter_tb.sv']
        assert b.old.run(cmd,work,directory/'build.log',180)==0,(directory/'build.log').read_text()
        code=b.old.run([str(work/'obj/test')],directory,directory/'run.log',120);log=(directory/'run.log').read_text()
        assert code not in (0,124) and diagnostic in log,(code,diagnostic,log)
        checks.append(dict(depth=depth,mode=mode,passed=True,expected_failure=diagnostic,returncode=code))
(root/'summary.json').write_text(json.dumps(dict(passed=True,source_sha256=b.old.hashes(['rtl/sync_bank.sv','rtl/buffered_transfer_controller.sv','tests/run_buffered_parameters.py']),cases=checks),indent=2)+'\n')
print('PASS 3 parameter rejection cases')
