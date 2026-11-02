#!/usr/bin/env bash
# Build the entire evidence chain in a fresh source checkout. Never overwrite
# the development checkout's archived performance evidence.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/tool_env.sh
python3 - <<'PY'
from pathlib import Path
root = Path('results/raw')
protected = [root / name for name in ('single_buffer', 'memory_timing', 'double_buffer')]
if any(p.exists() for p in protected):
    raise SystemExit('Use a fresh source checkout: historical benchmark directories already exist. '
                     'Use the individual documented runners to resume your own runs.')
PY
mkdir -p build/reproduction
bash scripts/check_core.sh --quick
bash scripts/test.sh
bash scripts/test_memory_timing.sh
bash scripts/test_buffered.sh
bash scripts/benchmark.sh
python3 benchmarks/bootstrap_reference.py
bash scripts/benchmark_memory_timing.sh
bash scripts/benchmark_buffered.sh
bash scripts/test_stage5.sh
bash scripts/test_stage5_reset_phases.sh
python3 tests/audit_stage5.py
python3 benchmarks/report_core.py
python3 benchmarks/report_core.py --check
echo 'PASS fresh core reproduction: native tests, historical references, matched comparisons and audit'
