#!/usr/bin/env python3
"""Predeclared Stage 5 reset-phase addendum using the same native RTL binaries."""
import json
from pathlib import Path

import run_stage5 as stage5


def main():
    original = json.loads((stage5.OUT / 'summary.json').read_text())
    assert original['passed'] and original['outcomes'] == 220
    builds = stage5.Builds()
    rows = []
    for seed, profile, edge in ((202, 0, 5), (101, 3, 25)):
        for n in (8, 32):
            item = original['inputs'][f'{seed}_{n}']
            for mode in range(3):
                result = stage5.execute(builds, item, n, mode, 2, 1, profile, reset_at=edge)
                log = (stage5.ROOT / result['log']).read_text()
                witness = next(line for line in log.splitlines() if line.startswith('RESET_WITNESS '))
                result['reset_witness'] = witness
                rows.append(result)
        print('PASS six reset-phase outcomes', seed, edge, flush=True)
    assert len(rows) == 12 and all(row['passed'] for row in rows)
    report = dict(passed=True, outcomes=12, source_sha256=stage5.bench.old.hashes(
        stage5.SOURCES + ['tests/run_stage5.py', 'tests/run_stage5_reset_phases.py']),
        main_source_sha256=original['source_sha256'], records=rows)
    (stage5.OUT / 'reset-phases.json').write_text(json.dumps(report, indent=2) + '\n')
    print('PASS 12 supplemental shared-reset outcomes', flush=True)


if __name__ == '__main__':
    main()
