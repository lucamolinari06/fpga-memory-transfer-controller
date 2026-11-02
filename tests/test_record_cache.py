#!/usr/bin/env python3
"""Compile and execute cache RTL; named failures cannot pass on timeout/build errors."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/record_cache'
SOURCES = ['rtl/record_cache.sv', 'sim/tb/record_cache_tb.sv', 'tests/test_record_cache.py',
           'scripts/test_record_cache.sh']
CASES = [('hits_collisions_stalls', None), ('reset_pending', None), ('reset_refill', None),
         ('reset_held_hit', None), ('reset_held_miss', None),
         ('reject_alignment', 'CACHE_REQUEST_BOUNDS'), ('reject_length', 'CACHE_REQUEST_BOUNDS'),
         ('reject_bounds', 'CACHE_REQUEST_BOUNDS'), ('reject_last', 'CACHE_RESPONSE_LAST'),
         ('checker_corrupt_data', 'CACHE_DATA_MISMATCH')]


def execute(argv, cwd, log, timeout):
    with log.open('w') as stream:
        result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                timeout=timeout, text=True)
    return result.returncode


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    hashes = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCES}
    report = dict(passed=False, source_sha256=hashes, stimulus='fixed directed schedules; no random seed',
                  verilator=subprocess.check_output(['verilator', '--version'], text=True).strip(), cases=[])
    # Native compiler uses a path without spaces; binaries are disposable.
    with tempfile.TemporaryDirectory(prefix='fpga-record-cache-') as temp:
        work = Path(temp)
        for name in SOURCES[:2]:
            shutil.copy2(ROOT / name, work / Path(name).name)
        fixture = OUT / 'fixture.hex'
        fixture.write_text(''.join(f'{((address * 0x9e3779b1) & 0xffffffff) ^ 0xa5c31f27:08x}\n'
                                   for address in range(2048)))
        report['fixture_sha256'] = hashlib.sha256(fixture.read_bytes()).hexdigest()
        command = ['verilator', '--binary', '--timing', '--assert', '-Wall', '--top-module',
                   'record_cache_tb', '--Mdir', 'obj', '-o', 'cache_test', '-j', '2',
                   'record_cache.sv', 'record_cache_tb.sv']
        report['build_command'] = command
        code = execute(command, work, OUT / 'build.log', 180)
        if code:
            raise RuntimeError((OUT / 'build.log').read_text())
        for index, (name, expected) in enumerate(CASES):
            command = [str(work / 'obj/cache_test'), f'+fixture={fixture}', f'+scenario={index}']
            log = OUT / f'{name}.log'
            code = execute(command, work, log, 20)
            text = log.read_text()
            passed = (code != 0 and expected in text and 'UNIT_TIMEOUT' not in text) if expected else (
                code == 0 and f'PASS record_cache scenario={index} ' in text)
            entry = dict(name=name, scenario=index, expected_failure=expected, exit_code=code,
                         passed=passed, command=command, log=str(log.relative_to(ROOT)))
            report['cases'].append(entry)
            if not passed:
                (OUT / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
                raise RuntimeError(f'{name} failed:\n{text}')
            print('PASS', name, flush=True)
    report['passed'] = True
    (OUT / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'PASS {len(CASES)} native cache outcomes', flush=True)


if __name__ == '__main__':
    main()
