#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/tool_env.sh
case "${1:-all}" in
    stage2) python3 tests/run_baseline.py ;;
    stage3) python3 tests/run_hybrid.py ;;
    all)
        python3 tests/run_baseline.py
        python3 tests/run_hybrid.py
        ;;
    *) echo 'Usage: bash scripts/test.sh [all|stage2|stage3]' >&2; exit 2 ;;
esac
