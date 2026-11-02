#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
source scripts/tool_env.sh
verilator --lint-only --timing --assert -Wall --top-module smoke_tb \
    rtl/smoke_counter.sv sim/tb/smoke_tb.sv
verilator --lint-only --timing --assert --trace -Wall --top-module baseline_tb \
    rtl/sync_bank.sv rtl/single_memory_controller.sv sim/models/behavioral_memory.sv \
    sim/models/stream_sink.sv sim/tb/address_scoreboard.sv sim/tb/baseline_tb.sv
verilator --lint-only --timing --assert -Wall --top-module memory_tb \
    sim/models/behavioral_memory.sv sim/tb/memory_tb.sv
verilator --lint-only --timing --assert --trace -Wall --top-module hybrid_tb \
    rtl/sync_bank.sv rtl/hybrid_controller.sv sim/models/behavioral_memory.sv \
    sim/models/stream_sink.sv sim/tb/address_scoreboard.sv sim/tb/hybrid_tb.sv
verilator --lint-only --timing --assert -Wall --top-module benchmark_tb \
    rtl/sync_bank.sv rtl/single_memory_controller.sv rtl/hybrid_controller.sv \
    sim/models/behavioral_memory.sv sim/models/stream_sink.sv \
    sim/tb/address_scoreboard.sv sim/tb/benchmark_tb.sv
verilator --lint-only --timing --assert --trace -Wall --top-module profiled_memory_tb \
    sim/models/timing_calendar.sv sim/models/profiled_memory_pair.sv \
    sim/tb/service_monitor.sv sim/tb/profiled_memory_tb.sv
verilator --lint-only --timing --assert --trace -Wall --top-module timing_benchmark_tb \
    rtl/sync_bank.sv rtl/single_memory_controller.sv rtl/hybrid_controller.sv \
    sim/models/timing_calendar.sv sim/models/profiled_memory_pair.sv sim/models/stream_sink.sv \
    sim/tb/service_monitor.sv sim/tb/address_scoreboard.sv sim/tb/timing_benchmark_tb.sv
for depth in 1 2; do
    for profiled in 0 1; do
        verilator --lint-only --timing --assert --trace -Wall --top-module buffered_benchmark_tb \
            -GBUFFER_COUNT="$depth" -GPROFILED="$profiled" \
            rtl/sync_bank.sv rtl/single_memory_controller.sv rtl/hybrid_controller.sv rtl/buffered_transfer_controller.sv \
            sim/models/behavioral_memory.sv sim/models/timing_calendar.sv sim/models/profiled_memory_pair.sv \
            sim/models/stream_sink.sv sim/tb/service_monitor.sv sim/tb/address_scoreboard.sv sim/tb/buffered_benchmark_tb.sv
done
done
for profiled in 0 1; do
    verilator --lint-only --timing --assert --trace -Wall --top-module stage5_stress_tb \
        -GPROFILED="$profiled" \
        rtl/sync_bank.sv rtl/single_memory_controller.sv rtl/hybrid_controller.sv rtl/buffered_transfer_controller.sv \
        sim/models/behavioral_memory.sv sim/models/timing_calendar.sv sim/models/profiled_memory_pair.sv \
        sim/tb/service_monitor.sv sim/tb/address_scoreboard.sv sim/tb/stage5_stress_tb.sv
done
