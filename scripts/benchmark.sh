#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/tool_env.sh
# Runner rejects missing, failed or stale correctness reports.
python3 benchmarks/run_single_buffer.py "$@"
