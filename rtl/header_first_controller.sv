// Conventional conditional-fetch control for the fixed record application.
// One record owns this serial controller until its final stream handshake.
module header_first_controller (
    input logic clk, rst,
    input logic [31:0] threshold,
    input logic cmd_valid,
    output logic cmd_ready,
    input logic [31:0] cmd_base_word,
    output logic a_req_valid,
    input logic a_req_ready,
    output logic [31:0] a_req_base_word,
    output logic [8:0] a_req_words,
    input logic a_rsp_valid,
    output logic a_rsp_ready,
    input logic [31:0] a_rsp_data,
    input logic a_rsp_last,
    output logic b_req_valid,
    input logic b_req_ready,
    output logic [31:0] b_req_base_word,
    output logic [8:0] b_req_words,
    input logic b_rsp_valid,
    output logic b_rsp_ready,
    input logic [31:0] b_rsp_data,
    input logic b_rsp_last,
    output logic out_valid,
    input logic out_ready,
    output logic [31:0] out_data,
    output logic out_last
);
    timeunit 1ns; timeprecision 1ps;
    typedef enum logic [2:0] {IDLE, A_REQUEST, A_RESPONSE, B_REQUEST,
                              B_RESPONSE, DRAIN} state_t;
    state_t state;
    logic [31:0] base, query_threshold;
    logic [4:0] committed, reads;
    logic selected, decision_valid, output_valid, output_last;
    logic a_fire, b_fire, read_fire, retire;
    logic [31:0] bank_data;

    assign cmd_ready = !rst && state == IDLE;
    assign a_req_valid = !rst && state == A_REQUEST;
    assign a_req_base_word = base;
    assign a_req_words = 9'd2;
    assign a_rsp_ready = !rst && state == A_RESPONSE;
    assign b_req_valid = !rst && state == B_REQUEST;
    assign b_req_base_word = base + 32'd2;
    assign b_req_words = 9'd14;
    assign b_rsp_ready = !rst && state == B_RESPONSE;
    assign a_fire = a_rsp_valid && a_rsp_ready;
    assign b_fire = b_rsp_valid && b_rsp_ready;
    assign out_valid = !rst && output_valid;
    assign out_data = bank_data;
    assign out_last = output_last;
    assign retire = out_valid && out_ready && out_last;
    assign read_fire = !rst && state != IDLE && reads < committed
        && (reads == 0 || decision_valid) && (!output_valid || out_ready);

    sync_bank #(.WORDS(16)) assembly (
        .clk,
        .wr_en(a_fire || b_fire), .wr_addr(9'(committed)),
        .wr_data(a_fire ? a_rsp_data : b_rsp_data),
        .rd_en(read_fire), .rd_addr(9'(reads)), .rd_data(bank_data)
    );

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= IDLE;
            base <= 0;
            query_threshold <= 0;
            committed <= 0;
            reads <= 0;
            selected <= 0;
            decision_valid <= 0;
            output_valid <= 0;
            output_last <= 0;
        end else begin
            if (out_valid && out_ready) output_valid <= 0;
            if (read_fire) begin
                reads <= reads + 1'b1;
                output_valid <= 1;
                output_last <= decision_valid && (selected ? reads == 15 : reads == 1);
            end
            if (a_fire || b_fire) committed <= committed + 1'b1;
            case (state)
                IDLE: if (cmd_valid && cmd_ready) begin
                    base <= cmd_base_word;
                    query_threshold <= threshold;
                    committed <= 0;
                    reads <= 0;
                    selected <= 0;
                    decision_valid <= 0;
                    output_valid <= 0;
                    output_last <= 0;
                    state <= A_REQUEST;
                end
                A_REQUEST: if (a_req_valid && a_req_ready) state <= A_RESPONSE;
                A_RESPONSE: if (a_fire && committed == 1) begin
                    selected <= a_rsp_data < query_threshold;
                    decision_valid <= 1;
                    state <= a_rsp_data < query_threshold ? B_REQUEST : DRAIN;
                end
                B_REQUEST: if (b_req_valid && b_req_ready) state <= B_RESPONSE;
                B_RESPONSE: if (b_fire && committed == 15) state <= DRAIN;
                DRAIN: if (retire) state <= IDLE;
                default: state <= IDLE;
            endcase
        end
    end

    // synthesis translate_off
    logic a_stalled, b_stalled, output_stalled;
    logic [40:0] held_a, held_b;
    logic [32:0] held_output;
    always @(posedge clk) begin
        if (rst) begin
            a_stalled <= 0;
            b_stalled <= 0;
            output_stalled <= 0;
            held_a <= 0;
            held_b <= 0;
            held_output <= 0;
        end else begin
            if (a_stalled)
                assert (a_req_valid && {a_req_base_word,a_req_words} == held_a)
                    else $fatal(1, "HEADER_A_REQUEST_UNSTABLE");
            if (b_stalled)
                assert (b_req_valid && {b_req_base_word,b_req_words} == held_b)
                    else $fatal(1, "HEADER_B_REQUEST_UNSTABLE");
            if (output_stalled)
                assert (out_valid && {out_data,out_last} == held_output)
                    else $fatal(1, "HEADER_OUTPUT_UNSTABLE");
            a_stalled <= a_req_valid && !a_req_ready;
            b_stalled <= b_req_valid && !b_req_ready;
            output_stalled <= out_valid && !out_ready;
            held_a <= {a_req_base_word,a_req_words};
            held_b <= {b_req_base_word,b_req_words};
            held_output <= {out_data,out_last};
            if (cmd_valid && cmd_ready)
                assert (cmd_base_word[3:0] == 0 && cmd_base_word < 2048)
                    else $fatal(1, "HEADER_COMMAND_ADDRESS");
            if (a_fire)
                assert (committed < 2 && a_rsp_last == (committed == 1))
                    else $fatal(1, "HEADER_A_RESPONSE_LENGTH");
            if (b_fire)
                assert (selected && committed >= 2 && committed < 16
                        && b_rsp_last == (committed == 15))
                    else $fatal(1, "HEADER_B_RESPONSE_LENGTH");
            assert (!(a_fire && b_fire) && committed <= 16 && reads <= committed)
                else $fatal(1, "HEADER_ACCOUNTING");
            if (retire)
                assert (state == DRAIN && decision_valid && reads == committed
                        && committed == (selected ? 16 : 2))
                    else $fatal(1, "HEADER_PREMATURE_RETIRE");
        end
    end
    // synthesis translate_on
endmodule
