// Application comparison: 1 KiB direct-mapped, read-only, whole-record cache.
// One request/miss, 16 lines x 16 words, synchronous hit reads. Shared reset
// invalidates tags and cancels the epoch; data arrays are intentionally not reset.
module record_cache (
    input logic clk, rst,
    input logic req_valid,
    output logic req_ready,
    input logic [31:0] req_base_word,
    input logic [8:0] req_words,
    output logic rsp_valid,
    input logic rsp_ready,
    output logic [31:0] rsp_data,
    output logic rsp_last,
    output logic mem_req_valid,
    input logic mem_req_ready,
    output logic [31:0] mem_req_base_word,
    output logic [8:0] mem_req_words,
    input logic mem_rsp_valid,
    output logic mem_rsp_ready,
    input logic [31:0] mem_rsp_data,
    input logic mem_rsp_last,
    output logic [31:0] hit_count, miss_count
);
    timeunit 1ns; timeprecision 1ps;
    typedef enum logic [1:0] {IDLE, HIT, MISS_REQUEST, MISS_DATA} state_t;
    state_t state;
    logic [31:0] data [0:255];
    logic [23:0] tags [0:15];
    logic [15:0] valid_lines;
    logic [31:0] base;
    logic [3:0] line;
    logic [4:0] next_word;
    logic held_valid, held_last;
    logic [31:0] held_data;

    assign req_ready = !rst && state == IDLE;
    assign rsp_valid = !rst && held_valid;
    assign rsp_data = held_data;
    assign rsp_last = held_last;
    assign mem_req_valid = !rst && state == MISS_REQUEST;
    assign mem_req_base_word = base;
    assign mem_req_words = 9'd16;
    assign mem_rsp_ready = !rst && state == MISS_DATA && next_word < 16
                           && (!held_valid || rsp_ready);

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            valid_lines <= '0;
            base <= 0;
            line <= 0;
            next_word <= 0;
            held_valid <= 0;
            held_last <= 0;
            held_data <= 0;
            hit_count <= 0;
            miss_count <= 0;
        end else begin
            if (rsp_valid && rsp_ready) held_valid <= 0;
            case (state)
                IDLE: if (req_valid && req_ready) begin
                    assert (req_base_word[3:0] == 0 && req_words == 16
                            && req_base_word < 2048)
                        else $fatal(1, "CACHE_REQUEST_BOUNDS");
                    base <= req_base_word;
                    line <= req_base_word[7:4];
                    next_word <= 0;
                    if (valid_lines[req_base_word[7:4]]
                        && tags[req_base_word[7:4]] == req_base_word[31:8]) begin
                        state <= HIT;
                        hit_count <= hit_count + 1;
                    end else begin
                        // Never make a partially overwritten line visible.
                        valid_lines[req_base_word[7:4]] <= 0;
                        state <= MISS_REQUEST;
                        miss_count <= miss_count + 1;
                    end
                end
                HIT: begin
                    if (next_word < 16 && (!held_valid || rsp_ready)) begin
                        held_data <= data[{line, next_word[3:0]}];
                        held_last <= next_word == 15;
                        held_valid <= 1;
                        next_word <= next_word + 1;
                    end
                    if (rsp_valid && rsp_ready && rsp_last) state <= IDLE;
                end
                MISS_REQUEST: if (mem_req_valid && mem_req_ready) state <= MISS_DATA;
                MISS_DATA: begin
                    if (mem_rsp_valid && mem_rsp_ready) begin
                        assert (mem_rsp_last == (next_word == 15))
                            else $fatal(1, "CACHE_RESPONSE_LAST");
                        data[{line, next_word[3:0]}] <= mem_rsp_data;
                        held_data <= mem_rsp_data;
                        held_last <= mem_rsp_last;
                        held_valid <= 1;
                        next_word <= next_word + 1;
                        if (mem_rsp_last) begin
                            tags[line] <= base[31:8];
                            valid_lines[line] <= 1;
                        end
                    end
                    if (rsp_valid && rsp_ready && rsp_last) state <= IDLE;
                end
                default: state <= IDLE;
            endcase
        end
    end
    assert property (@(posedge clk) disable iff (rst)
        rsp_valid && !rsp_ready |=> rsp_valid && $stable({rsp_data, rsp_last}))
        else $fatal(1, "CACHE_RESPONSE_STABILITY");
    assert property (@(posedge clk) disable iff (rst)
        mem_req_valid && !mem_req_ready |=> mem_req_valid
        && $stable({mem_req_base_word, mem_req_words}))
        else $fatal(1, "CACHE_REQUEST_STABILITY");
endmodule
