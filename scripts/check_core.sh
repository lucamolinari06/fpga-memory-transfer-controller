#!/usr/bin/env bash
# Re-run native correctness and audit the preserved benchmark evidence.
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/tool_env.sh
exec python3 tests/check_core.py "$@"
