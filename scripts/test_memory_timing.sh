#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/tool_env.sh
python3 tests/run_memory_timing.py
python3 benchmarks/run_memory_timing.py --verify-only
python3 benchmarks/test_timing_measurements.py
