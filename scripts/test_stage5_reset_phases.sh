#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/tool_env.sh
python3 tests/run_stage5_reset_phases.py
