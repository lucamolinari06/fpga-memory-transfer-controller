#!/usr/bin/env python3
"""Audit the executed native Stage 5 matrix, pairing and retained inputs."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'benchmarks'))
import run_double_buffer as stage4
import run_stage5 as stage5


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root = ROOT / 'build/stage5'
    report = json.loads((root / 'summary.json').read_text())
    assert report['passed'] and report['outcomes'] == 220
    assert report['source_sha256'] == stage4.old.hashes(stage5.SOURCES + ['tests/run_stage5.py'])
    records = report['records']
    assert len(records) == 220 and all(r['passed'] for r in records)
    primary = [r for r in records if not r['reset_at'] and not r['fault']]
    reset = [r for r in records if r['reset_at']]
    faults = [r for r in records if r['fault']]
    assert len(primary) == 200 and len(reset) == 12 and len(faults) == 8
    matrix = {(r['seed'], r['n'], r['profile'], r['mode'], r['depth'], r['early'])
              for r in primary}
    assert len(matrix) == 192
    assert {r['fault'] for r in faults} == {1, 2, 3, 5, 6, 7, 8, 9}
    assert Counter(r['tag'] for r in primary).most_common(1)[0][1] == 9
    for item in report['inputs'].values():
        for key in ('schedule', 'calendar', 'bases'):
            path = Path(item[key])
            assert path.exists() and sha(path) == item['hashes'][path.name]
        schedule = Path(item['schedule'])
        assert schedule.stat().st_size == stage5.LENGTH * 3
        # Recalculate the exact exogenous file independently of stored hashes.
        with schedule.open() as f:
            for cycle, line in enumerate(f):
                assert int(line, 16) == stage5.sample(item['seed'], cycle)
            assert cycle + 1 == stage5.LENGTH
    for record in records:
        item = report['inputs'][f"{record['seed']}_{record['n']}"]
        assert record['input_hashes'] == item['hashes']
        result = json.loads((root / 'runs' / record['tag'] / 'result.json').read_text())
        assert result == record
        log = (ROOT / record['log']).read_text()
        if record['fault']:
            assert record['exit_code'] not in (0, 124)
            assert record['expected'] in log and 'FAULT_NOT_INJECTED' not in log
            controls = [r for r in primary if r['tag'] == record['tag'].rsplit('_f', 1)[0] + '_f0']
            assert len(controls) == 9 and all(r['input_hashes'] == record['input_hashes'] for r in controls)
        else:
            assert record['exit_code'] == 0 and 'PASS benchmark' in log
    protected = json.loads((ROOT / 'results/raw/double_buffer/summary.json').read_text())
    assert protected['passed']
    assert protected['source_sha256'] == stage4.old.hashes(protected['source_sha256'])
    supplemental = json.loads((root / 'reset-phases.json').read_text())
    assert supplemental['passed'] and supplemental['outcomes'] == 12
    assert supplemental['source_sha256'] == stage4.old.hashes(
        stage5.SOURCES + ['tests/run_stage5.py', 'tests/run_stage5_reset_phases.py'])
    assert supplemental['main_source_sha256'] == report['source_sha256']
    for record in supplemental['records']:
        assert record['passed'] and record['reset_at'] in (5, 25)
        assert 'RESET_WITNESS occupied=' in record['reset_witness']
        assert 'RESET_WITNESS occupied=0' not in record['reset_witness']
        log = (ROOT / record['log']).read_text()
        assert record['reset_witness'] in log and 'PASS benchmark' in log
        item = report['inputs'][f"{record['seed']}_{record['n']}"]
        assert record['input_hashes'] == item['hashes']
    summary = dict(passed=True, outcomes=len(records), distinct_clean=len(matrix),
                   reset=len(reset), supplemental_reset=len(supplemental['records']),
                   paired_faults=len(faults),
                   input_files=len({p for item in report['inputs'].values()
                                    for p in (item['schedule'], item['calendar'], item['bases'])}),
                   original_stage4_source_unchanged=True)
    (root / 'audit.json').write_text(json.dumps(summary, indent=2) + '\n')
    print('PASS Stage 5 matrix, inputs, fault pairs, sources and Stage 4 preservation', summary)


if __name__ == '__main__':
    main()
