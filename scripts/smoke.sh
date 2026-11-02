#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/tool_env.sh
mkdir -p build
(
    command -v verilator >/dev/null || { echo 'Missing Verilator; see docs/setup.md' >&2; exit 1; }
    # Avoid whitespace in generated Makefile paths, even when checkout path has spaces.
    work_dir=$(mktemp -d "${TMPDIR:-/tmp}/fpga-smoke.XXXXXX")
    trap 'rm -rf "$work_dir"' EXIT
    cp rtl/smoke_counter.sv sim/tb/smoke_tb.sv "$work_dir/"
    cd "$work_dir"
    verilator --binary --timing --assert -Wall --top-module smoke_tb \
        --Mdir obj_dir -o smoke smoke_counter.sv smoke_tb.sv
    ./obj_dir/smoke
) 2>&1 | tee build/smoke.log
