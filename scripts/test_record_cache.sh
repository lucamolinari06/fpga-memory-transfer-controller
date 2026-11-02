#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/tool_env.sh
python3 tests/test_record_cache.py
