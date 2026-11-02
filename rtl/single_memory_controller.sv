module single_memory_controller #(
    parameter int unsigned BLOCK_WORDS = 8,
    parameter int unsigned SPLIT_WORDS = 3,
    parameter bit USE_B = 0,
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
    typedef enum logic [1:0] {FREE, REQUEST, ACTIVE} state_t;
    state_t state;
    logic [31:0] base_word;
    logic [8:0] received, prefix_committed, suffix_committed;
    logic [8:0] read_issued, consumed;
    logic output_valid, output_last, output_suffix;
    logic req_ready, rsp_valid, rsp_last, rsp_ready;
    logic [31:0] rsp_data, prefix_data, suffix_data;
    logic write_fire, read_fire, read_suffix, write_prefix, readable;
    logic [8:0] read_addr, write_addr;

    assign cmd_ready = !rst && state == FREE;
    assign req_ready = USE_B ? b_req_ready : a_req_ready;
    assign rsp_valid = USE_B ? b_rsp_valid : a_rsp_valid;
    assign rsp_data = USE_B ? b_rsp_data : a_rsp_data;
    assign rsp_last = USE_B ? b_rsp_last : a_rsp_last;
    assign rsp_ready = !rst && state == ACTIVE && received < 9'(BLOCK_WORDS);
    assign a_req_valid = !rst && !USE_B && state == REQUEST;
    assign b_req_valid = !rst && USE_B && state == REQUEST;
    assign a_req_base_word = USE_B ? 32'd0 : base_word;
    assign b_req_base_word = USE_B ? base_word : 32'd0;
    assign a_req_words = USE_B ? 9'd0 : 9'(BLOCK_WORDS);
    assign b_req_words = USE_B ? 9'(BLOCK_WORDS) : 9'd0;
    assign a_rsp_ready = !USE_B && rsp_ready;
    assign b_rsp_ready = USE_B && rsp_ready;
    assign write_fire = rsp_valid && rsp_ready;
    assign out_valid = !rst && output_valid;
    assign out_last = output_last;
    assign out_data = output_suffix ? suffix_data : prefix_data;

    if (SPLIT_WORDS == 0) begin : g_all_suffix
        assign read_suffix = 1'b1;
        assign write_prefix = 1'b0;
    end else begin : g_partition
        assign read_suffix = read_issued >= 9'(SPLIT_WORDS);
        assign write_prefix = received < 9'(SPLIT_WORDS);
    end
    assign read_addr = read_suffix ? read_issued - 9'(SPLIT_WORDS) : read_issued;
    assign write_addr = write_prefix ? received : received - 9'(SPLIT_WORDS);
    assign readable = read_suffix ? read_addr < suffix_committed : read_addr < prefix_committed;
    assign read_fire = !rst && state == ACTIVE && read_issued < 9'(BLOCK_WORDS)
                       && readable && (!output_valid || out_ready)
                       && (EARLY_DELIVERY || received == 9'(BLOCK_WORDS));

    if (SPLIT_WORDS > 0) begin : g_prefix
        // Keep illegal configurations safe to elaborate so the named parameter check can reject them.
        sync_bank #(.WORDS(SPLIT_WORDS <= 256 ? SPLIT_WORDS : 1)) bank (
            .clk, .wr_en(write_fire && write_prefix),
            .wr_addr(write_addr), .wr_data(rsp_data),
            .rd_en(read_fire && !read_suffix), .rd_addr(read_addr), .rd_data(prefix_data)
        );
    end else begin : g_no_prefix
        assign prefix_data = 32'd0;
    end
    if (BLOCK_WORDS > SPLIT_WORDS) begin : g_suffix
        sync_bank #(.WORDS(SUFFIX_WORDS)) bank (
            .clk, .wr_en(write_fire && !write_prefix),
            .wr_addr(write_addr), .wr_data(rsp_data),
            .rd_en(read_fire && read_suffix), .rd_addr(read_addr), .rd_data(suffix_data)
        );
    end else begin : g_no_suffix
        assign suffix_data = 32'd0;
    end

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= FREE;
            base_word <= 0;
            received <= 0;
            prefix_committed <= 0;
            suffix_committed <= 0;
            read_issued <= 0;
            consumed <= 0;
            output_valid <= 0;
            output_last <= 0;
            output_suffix <= 0;
        end else begin
            if (cmd_valid && cmd_ready) begin
                state <= REQUEST;
                base_word <= cmd_base_word;
                received <= 0;
                prefix_committed <= 0;
                suffix_committed <= 0;
                read_issued <= 0;
                consumed <= 0;
            end
            if (state == REQUEST && req_ready) state <= ACTIVE;
            if (write_fire) begin
                received <= received + 9'd1;
                if (write_prefix) prefix_committed <= prefix_committed + 9'd1;
                else suffix_committed <= suffix_committed + 9'd1;
            end
            if (read_fire) begin
                read_issued <= read_issued + 9'd1;
                output_valid <= 1;
                output_suffix <= read_suffix;
                output_last <= read_issued == 9'(BLOCK_WORDS-1);
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
    always @(posedge clk) if (!rst) begin
        if (cmd_valid && cmd_ready) begin
            assert ((cmd_base_word % BLOCK_WORDS) == 0) else $fatal(1, "COMMAND_ALIGNMENT");
            assert (({1'b0, cmd_base_word} + 33'(BLOCK_WORDS-1)) <= 33'h0ffffffff)
                else $fatal(1, "COMMAND_OVERFLOW");
        end
        assert (consumed <= read_issued && read_issued <= received && received <= 9'(BLOCK_WORDS))
            else $fatal(1, "COUNT_ORDER");
        assert (prefix_committed <= 9'(SPLIT_WORDS) && suffix_committed <= 9'(SUFFIX_WORDS)
                && received == prefix_committed + suffix_committed) else $fatal(1, "COMMITTED_BOUNDS");
        assert (read_issued - consumed == 9'(output_valid)) else $fatal(1, "OUTPUT_OWNERSHIP");
        if (rsp_valid) assert (state == ACTIVE && received < 9'(BLOCK_WORDS))
            else $fatal(1, "UNSOLICITED_RESPONSE");
        if (write_fire) assert (rsp_last == (received == 9'(BLOCK_WORDS-1)))
            else $fatal(1, "RESPONSE_LAST");
        if (out_valid && out_ready && out_last)
            assert (received == 9'(BLOCK_WORDS) && read_issued == 9'(BLOCK_WORDS))
                else $fatal(1, "PREMATURE_FREE");
        if (state == FREE) assert (!output_valid && !write_fire && !read_fire)
            else $fatal(1, "FREE_SLOT_ACCESS");
    end
    // synthesis translate_on
endmodule
