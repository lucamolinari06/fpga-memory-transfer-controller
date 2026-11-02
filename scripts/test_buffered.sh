#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/tool_env.sh
python3 tests/run_buffered.py
python3 tests/run_buffered_extra.py
python3 tests/run_buffered_parameters.py
python3 benchmarks/test_buffered_measurements.py
