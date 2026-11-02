module baseline_tb #(
    parameter int unsigned BLOCK_WORDS = 8,
    parameter int unsigned SPLIT_WORDS = 3,
    parameter bit USE_B = 0
);
    timeunit 1ns; timeprecision 1ps;
    logic clk, rst, cmd_valid, cmd_ready;
    logic [31:0] cmd_base_word;
    logic a_req_valid, a_req_ready, a_rsp_valid, a_rsp_ready, a_rsp_last;
    logic b_req_valid, b_req_ready, b_rsp_valid, b_rsp_ready, b_rsp_last;
    logic [31:0] a_req_base_word, b_req_base_word, a_rsp_data, b_rsp_data;
    logic [8:0] a_req_words, b_req_words;
    logic out_valid, out_ready, out_last;
    logic [31:0] out_data, checked_data;
    int unsigned latency, interval_cycles, burst_words, burst_gap, cooldown_cycles;
    int unsigned accept_period, accept_cycles, sink_period, sink_cycles, stall_start, stall_length;
    int unsigned blocks_to_send, reset_case, expect_early, expect_stall, expect_req_stall, expect_last_stall;
    int unsigned pending_words, checked_words, checked_blocks;
    longint unsigned sink_words, sink_blocks, sink_checksum, expected_checksum;
    int unsigned sent, epoch;
    bit inject_corruption, bad_alignment;
    logic req_valid, req_ready, rsp_valid, rsp_ready, rsp_last;
    logic [31:0] req_base;
    logic [8:0] req_words;
    longint unsigned cycle, request_edge, last_response_edge, last_consumption_edge;
    int unsigned responses, requests, consumed_in_block, early_words, held_cycles, request_stalls, held_last_cycles;
    bit request_owned;
    logic [31:0] requested_base, accepted_base;
    longint unsigned arrival_edge [0:255];
    int event_file;
    string event_path;
    initial clk = 0;
    always #5 clk <= ~clk;

    single_memory_controller #(.BLOCK_WORDS(BLOCK_WORDS), .SPLIT_WORDS(SPLIT_WORDS), .USE_B(USE_B)) dut (.*);
    behavioral_memory memory_a (
        .clk, .rst, .latency, .interval_cycles, .burst_words, .burst_gap, .cooldown_cycles,
        .accept_period, .accept_cycles, .req_valid(a_req_valid), .req_ready(a_req_ready),
        .req_base_word(a_req_base_word), .req_words(a_req_words), .rsp_valid(a_rsp_valid),
        .rsp_ready(a_rsp_ready), .rsp_data(a_rsp_data), .rsp_last(a_rsp_last)
    );
    behavioral_memory memory_b (
        .clk, .rst, .latency, .interval_cycles, .burst_words, .burst_gap, .cooldown_cycles,
        .accept_period, .accept_cycles, .req_valid(b_req_valid), .req_ready(b_req_ready),
        .req_base_word(b_req_base_word), .req_words(b_req_words), .rsp_valid(b_rsp_valid),
        .rsp_ready(b_rsp_ready), .rsp_data(b_rsp_data), .rsp_last(b_rsp_last)
    );
    assign checked_data = out_data ^ (inject_corruption ? 32'd1 : 32'd0);
    stream_sink sink (
        .clk, .rst, .period_cycles(sink_period), .ready_cycles(sink_cycles), .stall_start, .stall_length,
        .valid(out_valid), .ready(out_ready), .data(checked_data), .last(out_last),
        .words(sink_words), .blocks(sink_blocks), .checksum(sink_checksum)
    );
    address_scoreboard #(.BLOCK_WORDS(BLOCK_WORDS)) scoreboard (
        .clk, .rst, .cmd_valid, .cmd_ready, .cmd_base_word, .out_valid, .out_ready,
        .out_data(checked_data), .out_last, .pending_words, .checked_words, .checked_blocks, .expected_checksum
    );
    assign req_valid = USE_B ? b_req_valid : a_req_valid;
    assign req_ready = USE_B ? b_req_ready : a_req_ready;
    assign req_base = USE_B ? b_req_base_word : a_req_base_word;
    assign req_words = USE_B ? b_req_words : a_req_words;
    assign rsp_valid = USE_B ? b_rsp_valid : a_rsp_valid;
    assign rsp_ready = USE_B ? b_rsp_ready : a_rsp_ready;
    assign rsp_last = USE_B ? b_rsp_last : a_rsp_last;

    // Test drivers change at falling edges; only this process drives command payload.
    always @(negedge clk) begin
        cmd_valid <= !rst && sent < blocks_to_send;
        cmd_base_word <= 32'(256 + epoch*8192 + sent*BLOCK_WORDS + int'(bad_alignment));
    end
    // Independent public-channel monitor, intentionally imperative simulation logic.
    /* verilator lint_off BLKSEQ */
    always @(posedge clk) begin
        if (rst) begin
            sent = 0;
            cycle = 0;
            requests = 0;
            responses = 0;
            consumed_in_block = 0;
            early_words = 0;
            held_cycles = 0;
            held_last_cycles = 0;
            request_stalls = 0;
            request_owned = 0;
            request_edge = 0;
            last_response_edge = 0;
            last_consumption_edge = 0;
            requested_base = 0;
            accepted_base = 0;
            $fdisplay(event_file, "%0d,reset,%0d,0,0", cycle, epoch);
        end else begin
            if (cmd_valid && cmd_ready) begin
                accepted_base = cmd_base_word;
                sent++;
                consumed_in_block = 0;
                $fdisplay(event_file, "%0d,command,%0d,%0d,%0d", cycle, epoch, cmd_base_word, BLOCK_WORDS);
            end
            if (req_valid && !req_ready) request_stalls++;
            if (req_valid && req_ready) begin
                assert (!request_owned && requests + 1 == sent) else $fatal(1, "REQUEST_OWNERSHIP_MONITOR");
                assert (req_base == accepted_base && int'(req_words) == BLOCK_WORDS)
                    else $fatal(1, "REQUEST_MAPPING");
                request_owned = 1;
                requested_base = req_base;
                request_edge = cycle;
                requests++;
                responses = 0;
                $fdisplay(event_file, "%0d,request,%0d,%0d,%0d", cycle, epoch, req_base, req_words);
            end
            if (rsp_valid && rsp_ready) begin
                assert (request_owned) else $fatal(1, "UNOWNED_RESPONSE_MONITOR");
                if (responses == 0)
                    assert (cycle == request_edge + 64'(latency)) else $fatal(1, "INITIAL_LATENCY");
                else
                    assert (cycle == last_response_edge + 64'(interval_cycles)
                            + ((responses % burst_words == 0) ? 64'(burst_gap) : 64'd0))
                        else $fatal(1, "BEAT_INTERVAL");
                assert (rsp_last == (responses == BLOCK_WORDS-1)) else $fatal(1, "MEMORY_LAST_MONITOR");
                arrival_edge[responses] = cycle;
                responses++;
                last_response_edge = cycle;
                if (rsp_last) request_owned = 0;
                $fdisplay(event_file, "%0d,response,%0d,%0d,%0d", cycle, epoch, requested_base+responses-1, int'(rsp_last));
            end
            if (out_valid && !out_ready) held_cycles++;
            if (out_valid && !out_ready && out_last) held_last_cycles++;
            if (out_valid && out_ready) begin
                assert (consumed_in_block < responses) else $fatal(1, "OUTPUT_BEFORE_ARRIVAL");
                assert (cycle >= arrival_edge[consumed_in_block] + 2) else $fatal(1, "SYNC_READ_LATENCY");
                if (consumed_in_block == 0 && sink_period == 1 && stall_length == 0)
                    assert (cycle == arrival_edge[0] + 2) else $fatal(1, "FIRST_WORD_LATENCY");
                if (consumed_in_block > 0 && sink_period == 1 && stall_length == 0)
                    assert (cycle == ((arrival_edge[consumed_in_block]+2 > last_consumption_edge+1)
                            ? arrival_edge[consumed_in_block]+2 : last_consumption_edge+1))
                        else $fatal(1, "UNEXPECTED_STREAM_BUBBLE");
                if (responses < BLOCK_WORDS) early_words++;
                $fdisplay(event_file, "%0d,consume,%0d,%0d,%0d", cycle, epoch, requested_base+consumed_in_block, int'(out_last));
                consumed_in_block++;
                last_consumption_edge = cycle;
            end
            if (USE_B) assert (!a_req_valid && !a_rsp_ready && !a_rsp_valid) else $fatal(1, "INACTIVE_A");
            else assert (!b_req_valid && !b_rsp_ready && !b_rsp_valid) else $fatal(1, "INACTIVE_B");
            cycle++;
        end
    end
    /* verilator lint_on BLKSEQ */

    initial begin
        rst = 1;
        epoch = 0;
        latency = USE_B ? 6 : 2;
        interval_cycles = USE_B ? 1 : 3;
        burst_words = 256; burst_gap = 0; cooldown_cycles = 0;
        accept_period = 1; accept_cycles = 1;
        sink_period = 1; sink_cycles = 1; stall_start = 0; stall_length = 0;
        blocks_to_send = 6; reset_case = 0;
        expect_early = 0; expect_stall = 0; expect_req_stall = 0; expect_last_stall = 0;
        inject_corruption = $test$plusargs("corrupt");
        bad_alignment = $test$plusargs("bad_alignment");
        void'($value$plusargs("latency=%d", latency));
        void'($value$plusargs("interval=%d", interval_cycles));
        void'($value$plusargs("burst=%d", burst_words));
        void'($value$plusargs("gap=%d", burst_gap));
        void'($value$plusargs("cooldown=%d", cooldown_cycles));
        void'($value$plusargs("accept_period=%d", accept_period));
        void'($value$plusargs("accept_cycles=%d", accept_cycles));
        void'($value$plusargs("sink_period=%d", sink_period));
        void'($value$plusargs("sink_cycles=%d", sink_cycles));
        void'($value$plusargs("stall_start=%d", stall_start));
        void'($value$plusargs("stall_length=%d", stall_length));
        void'($value$plusargs("blocks=%d", blocks_to_send));
        void'($value$plusargs("reset_case=%d", reset_case));
        void'($value$plusargs("expect_early=%d", expect_early));
        void'($value$plusargs("expect_stall=%d", expect_stall));
        void'($value$plusargs("expect_req_stall=%d", expect_req_stall));
        void'($value$plusargs("expect_last_stall=%d", expect_last_stall));
        if (!$value$plusargs("events=%s", event_path)) event_path = "events.csv";
        event_file = $fopen(event_path, "w");
        assert (event_file != 0) else $fatal(1, "EVENT_LOG_OPEN");
        $fdisplay(event_file, "edge,event,epoch,address,value");
        if ($test$plusargs("trace")) begin $dumpfile("failure.vcd"); $dumpvars; end
        repeat (3) @(negedge clk);
        rst = 0;
        // Observe public channels away from sampling edges, then cancel the epoch.
        if (reset_case != 0) begin
            case (reset_case)
                1: begin do @(negedge clk); while (!(req_valid && !req_ready)); end
                2: begin do @(negedge clk); while (!(request_owned && responses == 0)); end
                3: begin do @(negedge clk); while (!(responses > 0 && responses < BLOCK_WORDS)); end
                4: begin do @(negedge clk); while (!(out_valid && !out_ready)); end
                default: $fatal(1, "RESET_CASE");
            endcase
            rst = 1;
            epoch = 1;
            repeat (2) @(negedge clk);
            rst = 0;
        end
        do begin @(posedge clk); #1; end while (checked_blocks != blocks_to_send);
        repeat (20) begin @(posedge clk); #1; end
        assert (pending_words == 0 && requests == blocks_to_send && !request_owned && !out_valid && cmd_ready)
            else $fatal(1, "DRAIN_CHECK");
        assert (sink_words == 64'(checked_words) && sink_blocks == 64'(checked_blocks) && sink_checksum == expected_checksum)
            else $fatal(1, "SINK_ACCOUNTING");
        if (expect_early != 0) assert (early_words > 0) else $fatal(1, "EARLY_WITNESS_MISSING");
        if (expect_stall != 0) assert (held_cycles > 0) else $fatal(1, "STALL_WITNESS_MISSING");
        if (expect_req_stall != 0) assert (request_stalls > 0) else $fatal(1, "REQUEST_STALL_WITNESS_MISSING");
        if (expect_last_stall != 0) assert (held_last_cycles > 0) else $fatal(1, "LAST_STALL_WITNESS_MISSING");
        $display("PASS baseline N=%0d S=%0d B=%0d blocks=%0d words=%0d early=%0d held=%0d reset=%0d",
                 BLOCK_WORDS, SPLIT_WORDS, USE_B, checked_blocks, checked_words, early_words, held_cycles, reset_case);
        $fclose(event_file);
        $finish;
    end
    initial begin
        #2000000;
        $fatal(1, "TEST_TIMEOUT");
    end
endmodule
