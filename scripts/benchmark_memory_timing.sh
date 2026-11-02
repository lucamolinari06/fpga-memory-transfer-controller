#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/tool_env.sh
python3 - <<'PY'
from pathlib import Path
import sys
sys.path.insert(0,'benchmarks')
import run_single_buffer as reference
reference.OUT=Path.cwd()/'results/raw/memory_timing/p0'
reference.main()
PY
python3 benchmarks/check_memory_timing_reference.py
python3 benchmarks/run_memory_timing.py
python3 benchmarks/report_memory_timing.py
