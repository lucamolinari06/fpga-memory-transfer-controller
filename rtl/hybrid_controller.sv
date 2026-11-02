module hybrid_controller #(
    parameter int unsigned BLOCK_WORDS = 8,
    parameter int unsigned SPLIT_WORDS = 3,
    parameter bit EARLY_DELIVERY = 1
) (
    input logic clk, rst,
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
    localparam int unsigned SUFFIX_WORDS = BLOCK_WORDS >= SPLIT_WORDS ? BLOCK_WORDS-SPLIT_WORDS : 0;
    typedef enum logic {FREE, ALLOCATED} state_t;
    state_t state;
    logic [31:0] base_word;
    logic a_sent, b_sent;
    logic [8:0] prefix_committed, suffix_committed, read_issued, consumed;
    logic output_valid, output_last, output_suffix;
    logic a_write, b_write, read_fire, read_suffix, readable;
    logic [8:0] read_addr;
    logic [31:0] prefix_data, suffix_data;

    assign cmd_ready = !rst && state == FREE;
    assign a_req_base_word = base_word;
    assign b_req_base_word = base_word + 32'(SPLIT_WORDS);
    assign a_req_words = 9'(SPLIT_WORDS);
    assign b_req_words = 9'(SUFFIX_WORDS);
    // Each interface progresses independently; no joint-ready or both-requests-accepted gate.
    if (SPLIT_WORDS > 0) begin : g_a_channel
        assign a_req_valid = !rst && state == ALLOCATED && !a_sent;
        assign a_rsp_ready = !rst && state == ALLOCATED && a_sent && prefix_committed < 9'(SPLIT_WORDS);
    end else begin : g_no_a_channel
        assign a_req_valid = 1'b0;
        assign a_rsp_ready = 1'b0;
    end
    if (SUFFIX_WORDS > 0) begin : g_b_channel
        assign b_req_valid = !rst && state == ALLOCATED && !b_sent;
        assign b_rsp_ready = !rst && state == ALLOCATED && b_sent && suffix_committed < 9'(SUFFIX_WORDS);
    end else begin : g_no_b_channel
        assign b_req_valid = 1'b0;
        assign b_rsp_ready = 1'b0;
    end
    assign a_write = a_rsp_valid && a_rsp_ready;
    assign b_write = b_rsp_valid && b_rsp_ready;
    assign out_valid = !rst && output_valid;
    assign out_last = output_last;
    assign out_data = output_suffix ? suffix_data : prefix_data;
    if (SPLIT_WORDS == 0) begin : g_all_suffix
        assign read_suffix = 1'b1;
    end else begin : g_partition
        assign read_suffix = read_issued >= 9'(SPLIT_WORDS);
    end
    assign read_addr = read_suffix ? read_issued - 9'(SPLIT_WORDS) : read_issued;
    assign readable = read_suffix ? read_addr < suffix_committed : read_addr < prefix_committed;
    assign read_fire = !rst && state == ALLOCATED && read_issued < 9'(BLOCK_WORDS)
                      && readable && (!output_valid || out_ready)
                      && (EARLY_DELIVERY || prefix_committed+suffix_committed == 9'(BLOCK_WORDS));

    if (SPLIT_WORDS > 0) begin : g_prefix
        sync_bank #(.WORDS(SPLIT_WORDS <= 256 ? SPLIT_WORDS : 1)) bank (
            .clk, .wr_en(a_write), .wr_addr(prefix_committed), .wr_data(a_rsp_data),
            .rd_en(read_fire && !read_suffix), .rd_addr(read_addr), .rd_data(prefix_data)
        );
    end else begin : g_no_prefix
        assign prefix_data = 0;
        // Consume unused input explicitly only in verification to detect unsolicited traffic.
    end
    if (SUFFIX_WORDS > 0) begin : g_suffix
        sync_bank #(.WORDS(SUFFIX_WORDS <= 256 ? SUFFIX_WORDS : 1)) bank (
            .clk, .wr_en(b_write), .wr_addr(suffix_committed), .wr_data(b_rsp_data),
            .rd_en(read_fire && read_suffix), .rd_addr(read_addr), .rd_data(suffix_data)
        );
    end else begin : g_no_suffix
        assign suffix_data = 0;
    end
    always_ff @(posedge clk) begin
        if (rst) begin
            state <= FREE;
            base_word <= 0;
            a_sent <= 0; b_sent <= 0;
            prefix_committed <= 0; suffix_committed <= 0;
            read_issued <= 0; consumed <= 0;
            output_valid <= 0; output_last <= 0; output_suffix <= 0;
        end else begin
            if (cmd_valid && cmd_ready) begin
                state <= ALLOCATED;
                base_word <= cmd_base_word;
                a_sent <= 0; b_sent <= 0;
                prefix_committed <= 0; suffix_committed <= 0;
                read_issued <= 0; consumed <= 0;
            end
            if (a_req_valid && a_req_ready) a_sent <= 1;
            if (b_req_valid && b_req_ready) b_sent <= 1;
            if (a_write) prefix_committed <= prefix_committed + 9'd1;
            if (b_write) suffix_committed <= suffix_committed + 9'd1;
            if (read_fire) begin
                read_issued <= read_issued + 9'd1;
                output_valid <= 1;
                output_last <= read_issued == 9'(BLOCK_WORDS-1);
                output_suffix <= read_suffix;
            end else if (out_valid && out_ready) output_valid <= 0;
            if (out_valid && out_ready) begin
                consumed <= consumed + 9'd1;
                if (consumed == 9'(BLOCK_WORDS-1)) state <= FREE;
            end
        end
    end

    // synthesis translate_off
    initial begin
        assert (BLOCK_WORDS >= 1 && BLOCK_WORDS <= 256 && (BLOCK_WORDS & (BLOCK_WORDS-1)) == 0)
            else $fatal(1, "PARAM_BLOCK_WORDS");
        assert (SPLIT_WORDS <= BLOCK_WORDS) else $fatal(1, "PARAM_SPLIT_WORDS");
    end
    assert property (@(posedge clk) disable iff (rst)
        out_valid && !out_ready |=> out_valid && $stable({out_data, out_last}))
        else $fatal(1, "OUTPUT_STABILITY");
    assert property (@(posedge clk) disable iff (rst)
        a_req_valid && !a_req_ready |=> a_req_valid && $stable({a_req_base_word, a_req_words}))
        else $fatal(1, "A_REQUEST_STABILITY");
    assert property (@(posedge clk) disable iff (rst)
        b_req_valid && !b_req_ready |=> b_req_valid && $stable({b_req_base_word, b_req_words}))
        else $fatal(1, "B_REQUEST_STABILITY");
    // Protocol stability also checks data on zero-length/unused interfaces if a faulty source drives valid.
    assert property (@(posedge clk) disable iff (rst)
        a_rsp_valid && !a_rsp_ready |=> a_rsp_valid && $stable({a_rsp_data, a_rsp_last}))
        else $fatal(1, "A_RESPONSE_STABILITY");
    assert property (@(posedge clk) disable iff (rst)
        b_rsp_valid && !b_rsp_ready |=> b_rsp_valid && $stable({b_rsp_data, b_rsp_last}))
        else $fatal(1, "B_RESPONSE_STABILITY");
    always @(posedge clk) if (!rst) begin
        if (cmd_valid && cmd_ready) begin
            assert ((cmd_base_word % BLOCK_WORDS) == 0) else $fatal(1, "COMMAND_ALIGNMENT");
            assert (({1'b0, cmd_base_word} + 33'(BLOCK_WORDS-1)) <= 33'h0ffffffff)
                else $fatal(1, "COMMAND_OVERFLOW");
        end
        assert (prefix_committed <= 9'(SPLIT_WORDS) && suffix_committed <= 9'(SUFFIX_WORDS))
            else $fatal(1, "COMMITTED_BOUNDS");
        assert (consumed <= read_issued && read_issued <= prefix_committed+suffix_committed
                && read_issued <= 9'(BLOCK_WORDS)) else $fatal(1, "COUNT_ORDER");
        assert (read_issued-consumed == 9'(output_valid)) else $fatal(1, "OUTPUT_OWNERSHIP");
        if (a_rsp_valid) assert (state == ALLOCATED && a_sent && a_rsp_ready)
            else $fatal(1, "UNSOLICITED_A_RESPONSE");
        if (b_rsp_valid) assert (state == ALLOCATED && b_sent && b_rsp_ready)
            else $fatal(1, "UNSOLICITED_B_RESPONSE");
        if (a_write) assert (a_rsp_last == (prefix_committed == 9'(SPLIT_WORDS-1)))
            else $fatal(1, "A_RESPONSE_LAST");
        if (b_write) assert (b_rsp_last == (suffix_committed == 9'(SUFFIX_WORDS-1)))
            else $fatal(1, "B_RESPONSE_LAST");
        if (out_valid && out_ready && out_last)
            assert (prefix_committed == 9'(SPLIT_WORDS) && suffix_committed == 9'(SUFFIX_WORDS)
                    && read_issued == 9'(BLOCK_WORDS)) else $fatal(1, "PREMATURE_FREE");
        if (state == FREE) assert (!output_valid && !a_write && !b_write && !read_fire)
            else $fatal(1, "FREE_SLOT_ACCESS");
    end
    // synthesis translate_on
endmodule
