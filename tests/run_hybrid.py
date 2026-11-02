#!/usr/bin/env python3
"""Stage 3 directed RTL regression, including exact approved transaction tables."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from run_baseline import ROOT, dataset, run

OUT = ROOT / 'build' / 'stage3'
SOURCES = ['rtl/sync_bank.sv', 'rtl/hybrid_controller.sv', 'sim/models/behavioral_memory.sv',
           'sim/models/stream_sink.sv', 'sim/tb/address_scoreboard.sv', 'sim/tb/hybrid_tb.sv']


def check_example(path, example):
    """Fixed published expected edges, not a simulation of the DUT algorithm."""
    rows = list(csv.DictReader(path.open()))
    request_edges = [int(r['edge']) for r in rows if r['event'].startswith('request_')]
    assert len(request_edges) == 2 and request_edges[0] == request_edges[1]
    origin = request_edges[0]
    writes = [(int(r['edge'])-origin, int(r['address'])-256) for r in rows if r['event'].startswith('response_')]
    consumes = [(int(r['edge'])-origin, int(r['address'])-256) for r in rows if r['event'] == 'consume']
    holds = [(int(r['edge'])-origin, int(r['address'])-256) for r in rows if r['event'] == 'hold']
    if example == 'a_first':
        arrival = [2, 5, 8, 6, 7, 8, 9, 10]
        consumption = [4, 7, 10, 13, 14, 15, 16, 17]
        expected_holds = [(11, 3), (12, 3)]
    else:
        arrival = [7, 10, 13, 2, 3, 4, 5, 6]
        consumption = [9, 12, 15, 16, 17, 18, 19, 20]
        expected_holds = []
    assert sorted(writes) == sorted((edge, word) for word, edge in enumerate(arrival)), writes
    assert consumes == [(edge, word) for word, edge in enumerate(consumption)], consumes
    assert holds == expected_holds, holds


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', action='append', help='Run only named cases (repeatable); default runs all.')
    selected = parser.parse_args().case
    OUT.mkdir(parents=True, exist_ok=True)
    fixture = OUT / 'dataset.hex'
    dataset(fixture)
    cases = []
    def add(name, n=8, s=3, expected=None, example=None, **args):
        cases.append((name, n, s, args, expected, example))
    add('example_a_first', blocks=1, stall_start=12, stall_length=2, expect_a_first=1,
        expect_early=1, expect_dual_write=1, expect_hold=1, example='a_first')
    add('example_b_first', blocks=1, a_latency=7, b_latency=2, expect_b_first=1,
        expect_early=1, expect_b_complete_before_a=1, example='b_first')
    add('simultaneous_responses', a_latency=1, b_latency=1, a_interval=1, b_interval=1, expect_dual_write=1)
    add('consume_before_b_accepts', b_accept_period=31, b_accept_cycles=1, expect_a_before_b_request=1)
    add('b_complete_before_a_accepts', a_accept_period=31, a_accept_cycles=1,
        b_latency=1, expect_b_complete_before_a=1)
    add('periodic_sink', sink_period=7, sink_cycles=2, expect_hold=1)
    add('bursts_cooldowns', a_burst=2, a_gap=4, b_burst=2, b_gap=5, a_cooldown=17,
        b_cooldown=25, sink_period=5, sink_cycles=2, expect_hold=1)
    add('all_arrive_while_sink_stalled', a_latency=1, b_latency=1, a_interval=1,
        stall_start=0, stall_length=50, expect_hold=1)
    add('held_last', a_latency=1, b_latency=1, a_interval=1, stall_start=11,
        stall_length=30, expect_last_hold=1)
    add('reset_a_accepted_only', reset_case=1, b_accept_period=31)
    add('reset_b_accepted_only', reset_case=2, a_accept_period=31)
    add('reset_suffix_complete', reset_case=3, a_latency=30, b_latency=1)
    add('reset_partial_prefix', reset_case=4, a_interval=5)
    add('reset_held_output', reset_case=5, stall_start=0, stall_length=50)
    add('reset_held_last', reset_case=6, a_latency=1, b_latency=1, a_interval=1,
        stall_start=11, stall_length=30)
    for n, s in [(1,0),(1,1),(2,0),(2,1),(2,2),(8,0),(8,1),(8,7),(8,8),
                 (256,0),(256,1),(256,255),(256,256)]:
        add(f'boundary_{n}_{s}', n=n, s=s, blocks=4, sink_period=5, sink_cycles=3)
    add('checker_corruption', corrupt=True, expected='DATA_MISMATCH')
    add('reject_bad_a_last', bad_a_last=True, expected='A_RESPONSE_LAST')
    add('reject_block_3', n=3, s=1, expected='PARAM_BLOCK_WORDS')
    add('reject_split_9', s=9, expected='PARAM_SPLIT_WORDS')
    if selected:
        unknown = set(selected) - {case[0] for case in cases}
        if unknown:
            parser.error(f'Unknown cases: {sorted(unknown)}')
        cases = [case for case in cases if case[0] in selected]
    report = {'stage': 3, 'scope': 'selected' if selected else 'full', 'randomized': False, 'seed': None,
              'verilator': subprocess.check_output(['verilator', '--version'], text=True).strip(),
              'fixture_sha256': hashlib.sha256(fixture.read_bytes()).hexdigest(),
              'source_sha256': {s: hashlib.sha256((ROOT/s).read_bytes()).hexdigest()
                                for s in SOURCES + ['tests/run_hybrid.py','tests/run_baseline.py']}, 'cases': []}
    summary = OUT / ('selected-summary.json' if selected else 'summary.json')
    work = Path(tempfile.mkdtemp(prefix='fpga-stage3-'))
    report['work_directory'] = str(work)
    cache = {}
    success = False
    try:
        for source in SOURCES:
            shutil.copy2(ROOT/source, work/Path(source).name)
        for name, n, s, args, expected, example in cases:
            case_dir = OUT/name
            case_dir.mkdir(exist_ok=True)
            if (n,s) not in cache:
                obj = f'obj_{n}_{s}'
                cmd = ['verilator','--binary','--timing','--assert','--trace','-Wall',
                       '--top-module','hybrid_tb','--Mdir',obj,'-o','hybrid','-j','2',
                       f'-GBLOCK_WORDS={n}', f'-GSPLIT_WORDS={s}'] + [Path(p).name for p in SOURCES]
                if run(cmd, work, OUT/f'build_{n}_{s}.log') != 0:
                    raise RuntimeError(f'Build failed: {OUT / f"build_{n}_{s}.log"}')
                cache[n,s] = work/obj/'hybrid'
            cmd = [str(cache[n,s]), f'+dataset={fixture}', f'+events={case_dir / "events.csv"}']
            cmd += [f'+{k}' if value is True else f'+{k}={value}' for k,value in args.items()]
            code = run(cmd, case_dir, case_dir/'run.log', timeout=30)
            output = (case_dir/'run.log').read_text()
            passed = code == 0 and 'PASS hybrid' in output if expected is None else (
                code not in (0,124) and expected in output)
            trace_check = None
            if passed and example:
                try:
                    check_example(case_dir/'events.csv', example)
                    trace_check = 'PASS'
                except AssertionError as error:
                    trace_check = f'FAIL: {error}'
                    passed = False
            report['cases'].append({'name':name, 'N':n, 'S':s, 'args':args, 'expected_failure':expected,
                                    'exit_code':code, 'passed':passed, 'example_check':trace_check, 'command':cmd})
            summary.write_text(json.dumps(report, indent=2)+'\n')
            print(f'{"PASS" if passed else "FAIL"} {name}' + (f' (expected {expected})' if expected else ''), flush=True)
            if not passed:
                run(cmd+['+trace'], case_dir, case_dir/'trace-rerun.log', timeout=30)
                raise RuntimeError(f'Unexpected result; retained logs/trace: {case_dir}; {trace_check}')
        success = True
    finally:
        report['passed'] = success
        summary.write_text(json.dumps(report, indent=2)+'\n')
        if success:
            shutil.rmtree(work)
        else:
            print(f'Build products retained: {work}', flush=True)
    print(f'PASS Stage 3: {len(cases)} directed/negative cases; scope={report["scope"]}', flush=True)


if __name__ == '__main__':
    main()
