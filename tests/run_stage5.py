#!/usr/bin/env python3
"""Recorded-seed RTL stress and isolated scoreboard fault campaign."""
import argparse
import csv
import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'benchmarks'))
import run_double_buffer as bench
from timing_inputs import workload, write_calendar

OUT = ROOT / 'build/stage5'
SOURCES = [p if p != 'sim/tb/buffered_benchmark_tb.sv' else 'sim/tb/stage5_stress_tb.sv'
           for p in bench.SOURCES]
SEEDS = (101, 202, 303, 404)
KINDS = ('sequential', 'permuted', 'conflict', 'expanded')
LENGTH = 200000


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample(seed, cycle):
    # Every sixteenth edge opens all gates, bounding every deliberate off-run.
    if cycle % 16 == 0:
        return 63
    d = hashlib.sha256(f'stage5-v1|{seed}|{cycle}'.encode()).digest()
    thresholds = (160, 176, 208, 208, 192, 192)
    return sum((1 << i) for i, t in enumerate(thresholds) if d[i] < t)


def inputs():
    idir = OUT / 'inputs'
    idir.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for seed, kind in zip(SEEDS, KINDS):
        schedule = idir / f'schedule_{seed}.hex'
        schedule.write_text(''.join(f'{sample(seed, c):02x}\n' for c in range(LENGTH)))
        assert schedule.stat().st_size == LENGTH * 3
        assert schedule.read_text().splitlines()[0] == '3f'
        calendar = idir / f'calendar_{seed}.txt'
        if not calendar.exists():
            write_calendar(calendar, LENGTH, seed)
        for n in (8, 32):
            bases = idir / f'bases_{seed}_n{n}.hex'
            if not bases.exists():
                bases.write_text(''.join(f'{v:08x}\n' for v in workload(n, kind)))
            manifest[f'{seed}_{n}'] = dict(seed=seed, kind=kind, schedule=str(schedule),
                                         calendar=str(calendar), bases=str(bases),
                                         hashes={p.name: sha(p) for p in (schedule, calendar, bases)})
    return manifest


class Builds:
    def __init__(self):
        self.root = OUT / 'build_logs'
        self.root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256(json.dumps(bench.old.hashes(SOURCES), sort_keys=True).encode()).hexdigest()[:16]
        self.work = Path(tempfile.gettempdir()) / f'fpga-stage5-{digest}'
        self.work.mkdir(exist_ok=True)
        for p in SOURCES:
            shutil.copy2(ROOT / p, self.work / Path(p).name)
        self.fixture = self.work / 'dataset.hex'
        bench.old.dataset(self.fixture)
        self.cache = {}

    def build(self, n, s, mode, early, depth, profiled):
        key = (n, s, mode, early, depth, profiled)
        if key in self.cache:
            return self.cache[key]
        tag = '_'.join(map(str, key))
        exe = self.work / f'obj_{tag}/stress'
        if not exe.exists():
            command = ['verilator', '--binary', '--timing', '--assert', '--trace', '-Wall',
                       '--top-module', 'stage5_stress_tb', '--Mdir', f'obj_{tag}',
                       '-o', 'stress', '-j', '2']
            command += [f'-G{k}={v}' for k, v in zip(
                ('BLOCK_WORDS', 'SPLIT_WORDS', 'MODE', 'EARLY_DELIVERY', 'BUFFER_COUNT', 'PROFILED'), key)]
            command += [Path(p).name for p in SOURCES]
            log = self.root / f'build_{tag}.log'
            code = bench.old.run(command, self.work, log, 180)
            assert code == 0, (key, code, log.read_text())
            print('BUILT', tag, flush=True)
        self.cache[key] = exe
        return exe


def execute(builds, item, n, mode, depth, early, profile, reset_at=0, fault=0):
    seed, kind = item['seed'], item['kind']
    s = 3 if n == 8 else 8
    tag = f's{seed}_n{n}_p{profile}_m{mode}_d{depth}_e{early}_r{reset_at}_f{fault}'
    directory = OUT / 'runs' / tag
    directory.mkdir(parents=True, exist_ok=True)
    exe = builds.build(n, s, mode, early, depth, int(profile > 0))
    command = [str(exe), f'+dataset={builds.fixture}', f'+workload={item["bases"]}',
               f'+schedule={item["schedule"]}', f'+records={directory / "blocks.csv"}',
               '+blocks=8', '+warmup=1', f'+profile={profile}', '+progress_limit=20000',
               f'+fault={fault}', f'+reset_at={reset_at}']
    if profile:
        command.append(f'+calendar={item["calendar"]}')
    # These parameters are fixed per seed, not per DUT/mode; bounded periodic
    # acceptance and latency variation complements the byte-exact disturbances.
    command += [f'+{k}={v}' for k, v in {
        'a_latency': 2 + seed % 5, 'b_latency': 4 + seed % 9,
        'a_interval': 1 + seed % 3, 'b_interval': 1 + seed % 2,
        'a_burst': 3 + seed % 4, 'b_burst': 4 + seed % 5,
        'a_gap': 1 + seed % 3, 'b_gap': 2 + seed % 4,
        'a_cooldown': seed % 3, 'b_cooldown': seed % 4,
        'a_accept_period': 3 + seed % 5, 'a_accept_cycles': 2,
        'b_accept_period': 4 + seed % 5, 'b_accept_cycles': 2,
    }.items()]
    logpath = directory / 'run.log'
    code = bench.old.run(command, directory, logpath, 120)
    log = logpath.read_text()
    expected = {1: 'DATA_MISMATCH', 2: 'DATA_MISMATCH', 3: 'DATA_MISMATCH',
                5: 'DATA_MISMATCH', 6: 'OUTPUT_LAST_MISMATCH',
                7: 'OUTPUT_LAST_MISMATCH', 8: 'CHECKER_MISSING_FINAL',
                9: 'UNEXPECTED_OUTPUT'}.get(fault)
    passed = (code == 0 and 'PASS benchmark' in log and 'STRESS_WITNESS' in log) if not fault else \
             (code not in (0, 124) and expected in log and 'FAULT_NOT_INJECTED' not in log)
    if passed and not fault:
        with (directory / 'blocks.csv').open() as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 8 and int(rows[-1]['useful']) == 8*n
        if reset_at:
            assert 'RESET_WITNESS occupied=' in log and 'RESET_WITNESS occupied=0' not in log
    if not passed:
        bench.old.run(command + ['+trace'], directory, directory / 'trace-rerun.log', 120)
    record = dict(tag=tag, seed=seed, kind=kind, n=n, s=s, mode=mode, depth=depth, early=early,
                  profile=profile, reset_at=reset_at, fault=fault, expected=expected,
                  passed=passed, exit_code=code, command=command, input_hashes=item['hashes'],
                  log=str(logpath.relative_to(ROOT)))
    (directory / 'result.json').write_text(json.dumps(record, indent=2) + '\n')
    assert passed, (tag, code, log[-3500:])
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--pilot', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = inputs()
    builds = Builds()
    records = []
    if args.pilot:
        item = manifest['101_8']
        records.append(execute(builds, item, 8, 2, 2, 1, 0))
        (OUT / 'pilot.json').write_text(json.dumps(records, indent=2) + '\n')
        print('PASS pilot', flush=True)
        return
    for seed in SEEDS:
        for n in (8, 32):
            item = manifest[f'{seed}_{n}']
            for profile in (0, 3):
                for mode in range(3):
                    for depth in (1, 2):
                        for early in (0, 1):
                            records.append(execute(builds, item, n, mode, depth, early, profile))
            print('PASS 24 clean outcomes', seed, n, flush=True)
    for seed in (101, 303):
        for n in (8, 32):
            item = manifest[f'{seed}_{n}']
            for mode in range(3):
                records.append(execute(builds, item, n, mode, 2, 1, 0 if seed == 101 else 3, 12))
    item = manifest['202_8']
    for fault in (1, 2, 3, 5, 6, 7, 8, 9):
        records.append(execute(builds, item, 8, 2, 2, 1, 0))
        records.append(execute(builds, item, 8, 2, 2, 1, 0, fault=fault))
    assert len(records) == 220 and all(r['passed'] for r in records)
    summary = dict(passed=True, outcomes=len(records), clean=192, reset=12, fault_pairs=8,
                   source_sha256=bench.old.hashes(SOURCES + ['tests/run_stage5.py']),
                   fixture_sha256=sha(builds.fixture), inputs=manifest, platform=platform.platform(),
                   verilator=subprocess.check_output(['verilator', '--version'], text=True).strip(),
                   records=records)
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('PASS', len(records), 'Stage 5 native outcomes', flush=True)


if __name__ == '__main__':
    main()
