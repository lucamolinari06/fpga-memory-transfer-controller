#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/tool_env.sh
python3 benchmarks/run_double_buffer.py "$@"
