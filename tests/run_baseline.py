#!/usr/bin/env python3
"""Build actual SV with Verilator, execute directed cases, retain reproduction evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build' / 'stage2'
SOURCES = ['rtl/sync_bank.sv', 'rtl/single_memory_controller.sv',
           'sim/models/behavioral_memory.sv', 'sim/models/stream_sink.sv',
           'sim/tb/address_scoreboard.sv', 'sim/tb/baseline_tb.sv', 'sim/tb/memory_tb.sv']


def dataset(path):
    # Deliberately independent of the SV checker implementation and DUT routing.
    golden = {0: 0xa5a55a5a, 1: 0x43dcd40b, 256: 0xdd1f0b5a, 65535: 0x811ee0a9}
    values = [(address * 2654435761 + 2779077210) % (2**32) for address in range(65536)]
    assert all(values[a] == value for a, value in golden.items())
    path.write_text(''.join(f'{word:08x}\n' for word in values))


def run(cmd, cwd, log, timeout=120):
    with log.open('w') as stream:
        try:
            return subprocess.run(cmd, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                  timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            stream.write('\nRUNNER_TIMEOUT\n')
            return 124


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fixture = OUT / 'dataset.hex'
    dataset(fixture)
    report = {'stage': 2, 'randomized': False, 'seed': None,
              'verilator': subprocess.check_output(['verilator', '--version'], text=True).strip(),
              'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
              'source_sha256': {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in SOURCES},
              'cases': []}
    cases = []
    def add(name, n=8, s=3, b=0, expected=None, **args):
        cases.append((name, n, s, b, args, expected))
    for b in (0, 1):
        mode = 'B' if b else 'A'
        add(f'{mode}_default', b=b, expect_early=1)
        add(f'{mode}_minimum_latency', b=b, latency=1, interval=1, expect_early=1)
        add(f'{mode}_bursts_and_sink', b=b, latency=7, interval=2, burst=2, gap=4,
            cooldown=9, sink_period=7, sink_cycles=2, expect_stall=1)
        add(f'{mode}_request_stalls', b=b, accept_period=17, accept_cycles=1, expect_req_stall=1)
        add(f'{mode}_held_last', b=b, latency=1, interval=1, stall_start=11, stall_length=30,
            expect_stall=1, expect_last_stall=1)
        for reset in (1, 2, 3, 4):
            add(f'{mode}_reset_{reset}', b=b, reset_case=reset, latency=12, interval=3,
                accept_period=17, accept_cycles=1, stall_start=0, stall_length=50)
    for n, s, b in [(1, 0, 0), (1, 1, 1), (2, 1, 0), (2, 1, 1),
                    (8, 0, 0), (8, 8, 1), (8, 1, 0), (8, 7, 1),
                    (256, 0, 0), (256, 1, 0), (256, 255, 1), (256, 256, 1)]:
        add(f'boundary_{n}_{s}_{b}', n=n, s=s, b=b, sink_period=5, sink_cycles=3, blocks=4)
    add('checker_corruption', expected='DATA_MISMATCH', corrupt=True)
    add('reject_misalignment', expected='COMMAND_ALIGNMENT', bad_alignment=True)
    add('reject_block_3', n=3, s=1, expected='PARAM_BLOCK_WORDS')
    add('reject_block_257', n=257, s=1, expected='PARAM_BLOCK_WORDS')
    add('reject_split_9', s=9, expected='PARAM_SPLIT_WORDS')

    # Build outside the space-containing checkout; retained on any unexpected failure.
    work = Path(tempfile.mkdtemp(prefix='fpga-stage2-'))
    report['work_directory'] = str(work)
    cache = {}
    success = False
    try:
        for source in SOURCES:
            shutil.copy2(ROOT / source, work / Path(source).name)
        for name, n, s, b, args, expected in cases:
            key = (n, s, b)
            case_dir = OUT / name
            case_dir.mkdir(exist_ok=True)
            if key not in cache:
                obj = f'obj_{n}_{s}_{b}'
                cmd = ['verilator', '--binary', '--timing', '--assert', '--trace', '-Wall',
                       '--top-module', 'baseline_tb', '--Mdir', obj, '-o', 'baseline',
                       '-j', '2', f'-GBLOCK_WORDS={n}', f'-GSPLIT_WORDS={s}', f'-GUSE_B={b}']
                cmd += [Path(s).name for s in SOURCES]
                build_log = OUT / f'build_{n}_{s}_{b}.log'
                code = run(cmd, work, build_log)
                if code != 0:
                    raise RuntimeError(f'Build failed ({code}): {build_log}')
                cache[key] = work / obj / 'baseline'
            cmd = [str(cache[key]), f'+dataset={fixture}', f'+events={case_dir / "events.csv"}']
            cmd += [f'+{k}' if value is True else f'+{k}={value}' for k, value in args.items()]
            code = run(cmd, case_dir, case_dir / 'run.log', timeout=30)
            output = (case_dir / 'run.log').read_text()
            passed = (code == 0 and 'PASS baseline' in output) if expected is None else (
                code != 0 and code != 124 and expected in output)
            report['cases'].append({'name': name, 'N': n, 'S': s, 'use_b': b, 'args': args,
                                    'expected_failure': expected, 'exit_code': code, 'passed': passed,
                                    'command': cmd})
            (OUT / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
            print(f'{"PASS" if passed else "FAIL"} {name}' + (f' (expected {expected})' if expected else ''), flush=True)
            if not passed:
                run(cmd + ['+trace'], case_dir, case_dir / 'trace-rerun.log', timeout=30)
                raise RuntimeError(f'Unexpected result; log/trace: {case_dir}')
        model_cmd = ['verilator', '--binary', '--timing', '--assert', '-Wall', '--top-module', 'memory_tb',
                     '--Mdir', 'obj_memory', '-o', 'memory_test', '-j', '2', 'behavioral_memory.sv', 'memory_tb.sv']
        if run(model_cmd, work, OUT / 'build_memory.log') != 0:
            raise RuntimeError('Memory-model build failed; see build_memory.log')
        code = run([str(work / 'obj_memory' / 'memory_test'), f'+dataset={fixture}'],
                   work, OUT / 'memory_model.log', timeout=30)
        passed = code == 0 and 'PASS memory model' in (OUT / 'memory_model.log').read_text()
        report['cases'].append({'name': 'memory_model_backpressure', 'exit_code': code, 'passed': passed})
        if not passed:
            raise RuntimeError('Memory-model self-check failed; see memory_model.log')
        print('PASS memory_model_backpressure', flush=True)
        success = True
    finally:
        report['passed'] = success
        (OUT / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
        if success:
            shutil.rmtree(work)
        else:
            print(f'Build products retained: {work}', flush=True)
    print(f'PASS Stage 2: {len(report["cases"])} directed/negative cases; evidence: {OUT}', flush=True)


if __name__ == '__main__':
    main()
