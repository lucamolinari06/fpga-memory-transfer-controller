// Architectural timing model, not synthesizable and not a DDR device model.
module behavioral_memory (
    input logic clk, rst,
    input int unsigned latency, interval_cycles, burst_words, burst_gap, cooldown_cycles,
    input int unsigned accept_period, accept_cycles,
    input logic req_valid,
    output logic req_ready,
    input logic [31:0] req_base_word,
    input logic [8:0] req_words,
    output logic rsp_valid,
    input logic rsp_ready,
    output logic [31:0] rsp_data,
    output logic rsp_last
);
    timeunit 1ns; timeprecision 1ps;
    localparam int unsigned DATASET_WORDS = 65536;
    logic [31:0] fixture [0:DATASET_WORDS-1];
    string dataset_path;
    bit busy;
    int unsigned base_word, length, beat, wait_left, cooldown_left;
    longint unsigned cycle;
    initial begin
        if (!$value$plusargs("dataset=%s", dataset_path)) $fatal(1, "DATASET_REQUIRED");
        $readmemh(dataset_path, fixture);
    end
    assign req_ready = !rst && !busy && cooldown_left == 0
                       && (cycle % 64'(accept_period)) < 64'(accept_cycles);
    assign rsp_valid = !rst && busy && wait_left == 0;
    assign rsp_data = fixture[base_word + beat];
    assign rsp_last = beat + 1 == length;
    always @(posedge clk) begin
        if (rst) begin
            busy <= 0;
            base_word <= 0;
            length <= 0;
            beat <= 0;
            wait_left <= 0;
            cooldown_left <= 0;
            cycle <= 0;
        end else begin
            assert (latency >= 1 && interval_cycles >= 1 && burst_words >= 1
                    && accept_period >= 1 && accept_cycles >= 1 && accept_cycles <= accept_period)
                else $fatal(1, "MEMORY_CONFIG");
            cycle <= cycle + 1;
            if (cooldown_left > 0) cooldown_left <= cooldown_left - 1;
            if (req_valid && req_ready) begin
                assert (req_words > 0 && req_words <= 256
                        && 64'(req_base_word) + 64'(req_words) <= 64'(DATASET_WORDS))
                    else $fatal(1, "MEMORY_REQUEST_BOUNDS");
                busy <= 1;
                base_word <= req_base_word;
                length <= int'(req_words);
                beat <= 0;
                wait_left <= latency - 1;
            end else if (busy) begin
                if (wait_left > 0) wait_left <= wait_left - 1;
                else if (rsp_valid && rsp_ready) begin
                    if (rsp_last) begin
                        busy <= 0;
                        cooldown_left <= cooldown_cycles;
                    end else begin
                        beat <= beat + 1;
                        wait_left <= interval_cycles - 1
                                     + (((beat+1) % burst_words == 0) ? burst_gap : 0);
                    end
                end
            end
        end
    end
    assert property (@(posedge clk) disable iff (rst)
        rsp_valid && !rsp_ready |=> rsp_valid && $stable({rsp_data, rsp_last}))
        else $fatal(1, "MEMORY_RESPONSE_STABILITY");
endmodule
