// Simulation-only finite store. A holds packed headers; B is authoritative.
module application_memory #(
    parameter bit HEADER_MODE = 0,
    parameter int unsigned CAPACITY_WORDS = HEADER_MODE ? 256 : 2048
) (
    input logic clk, rst,
    input int unsigned latency, interval_cycles, accept_period, accept_cycles,
    input longint unsigned schedule_cycle,
    input logic load_valid,
    output logic load_ready,
    input logic [31:0] load_address, load_data,
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
    logic [31:0] storage [0:CAPACITY_WORDS-1];
    bit initialized [0:CAPACITY_WORDS-1];
    logic busy;
    int unsigned base, length, beat, wait_left;
    string fixture;
    initial begin
        assert (CAPACITY_WORDS == (HEADER_MODE ? 256 : 2048))
            else $fatal(1, "APP_MEMORY_CAPACITY");
        if (!HEADER_MODE) begin
            if (!$value$plusargs("fixture=%s", fixture)) $fatal(1, "APP_FIXTURE_REQUIRED");
            $readmemh(fixture, storage);
        end
    end
    assign load_ready = !rst && !busy;
    assign req_ready = !rst && !busy && !load_valid
                       && schedule_cycle % 64'(accept_period) < 64'(accept_cycles);
    assign rsp_valid = !rst && busy && wait_left == 0;
    assign rsp_data = storage[base + beat];
    assign rsp_last = beat + 1 == length;
    // Simulation-only validity array; a single process owns these flags.
    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin
        if (rst) begin
            busy <= 0; base <= 0; length <= 0; beat <= 0; wait_left <= 0;
            for (int i = 0; i < CAPACITY_WORDS; i++) initialized[i] = !HEADER_MODE;
        end else begin
            assert (latency >= 1 && interval_cycles >= 1 && accept_period >= 1
                    && accept_cycles >= 1 && accept_cycles <= accept_period)
                else $fatal(1, "APP_MEMORY_CONFIG");
            if (load_valid && load_ready) begin
                assert (load_address < CAPACITY_WORDS) else $fatal(1, "APP_LOAD_BOUNDS");
                storage[load_address] <= load_data;
                initialized[load_address] = 1;
            end
            if (req_valid && req_ready) begin
                assert (req_words > 0 && req_words <= 16
                        && 64'(req_base_word) + 64'(req_words) <= 2048)
                    else $fatal(1, "APP_MEMORY_BOUNDS");
                if (HEADER_MODE) begin
                    assert (req_base_word % 16 == 0 && req_words == 2)
                        else $fatal(1, "APP_HEADER_PLACEMENT");
                    assert (initialized[(req_base_word/16)*2]
                            && initialized[(req_base_word/16)*2+1])
                        else $fatal(1, "APP_HEADER_NOT_LOADED");
                end
                base <= HEADER_MODE ? (req_base_word/16)*2 : req_base_word;
                length <= int'(req_words); beat <= 0; wait_left <= latency-1; busy <= 1;
            end else if (busy) begin
                if (wait_left > 0) wait_left <= wait_left-1;
                else if (rsp_valid && rsp_ready) begin
                    if (rsp_last) busy <= 0;
                    else begin beat <= beat+1; wait_left <= interval_cycles-1; end
                end
            end
        end
    end
    /* verilator lint_on BLKSEQ */
    assert property (@(posedge clk) disable iff (rst)
        rsp_valid && !rsp_ready |=> rsp_valid && $stable({rsp_data,rsp_last}))
        else $fatal(1, "APP_MEMORY_RESPONSE_STABILITY");
endmodule
