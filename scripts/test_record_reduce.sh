#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/tool_env.sh
mkdir -p build/application-reducer
fpga_reduce_work=$(mktemp -d "${TMPDIR:-/tmp}/fpga-reduce.XXXXXX")
trap 'rm -rf "$fpga_reduce_work"' EXIT
cp rtl/record_reduce.sv sim/tb/record_reduce_tb.sv "$fpga_reduce_work/"
(
    cd "$fpga_reduce_work"
    verilator --binary --timing --assert -Wall --top-module record_reduce_tb \
        --Mdir obj_dir -o reduce record_reduce.sv record_reduce_tb.sv
) > build/application-reducer/build.log 2>&1
"$fpga_reduce_work/obj_dir/reduce" > build/application-reducer/positive.log 2>&1
for fault in 1 2; do
    if "$fpga_reduce_work/obj_dir/reduce" "+fault=$fault" > "build/application-reducer/fault-$fault.log" 2>&1; then
        echo "Expected reducer fault $fault did not fail" >&2
        exit 1
    fi
    case "$fault" in
        1) category=REDUCE_SHORT_SELECTED ;;
        2) category=REDUCE_RECORD_LENGTH ;;
    esac
    if ! grep -q "$category" "build/application-reducer/fault-$fault.log"; then
        echo "Reducer fault $fault failed with the wrong diagnostic" >&2
        exit 1
    fi
done
printf '%s\n' 'PASS: record reducer positive scenario and two named expected failures'
